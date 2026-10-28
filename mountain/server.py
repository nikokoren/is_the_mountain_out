"""Run: python -m mountain.server. Put a TLS reverse proxy in front for TRMNL polling."""
import argparse
import json
import secrets
import sqlite3
import time
from html import escape
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from mountain.provider import WeatherService
from mountain.feedback import FeedbackStore, public_origin, qr_svg
from mountain.feedback_page import form, page, receipt


def location_from(query):
    from mountain.viewpoints import VIEWPOINTS, MOUNTAINS
    if any(key in query for key in ('latitude', 'longitude', 'name')):
        raise ValueError('Use a named viewpoint to keep artwork and geometry aligned.')
    mountain = query.get('mountain', ['rainier'])[0].strip() or 'rainier'
    if mountain not in MOUNTAINS:
        raise ValueError('Unknown mountain')
    default = 'portland' if mountain == 'hood' else 'seattle'
    key = query.get('viewpoint', [default])[0].strip() or default
    if key not in VIEWPOINTS or VIEWPOINTS[key]['mountain'] != mountain:
        raise ValueError('Unknown viewpoint')
    return dict(VIEWPOINTS[key])



def handler(service, feedback_store=None, public_url=None):
    public_url = public_origin(public_url) if public_url else None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not retain client addresses, form values or QR/session tokens.
            path = urlsplit(self.path).path
            if path.startswith(('/f/', '/q/')):
                path = '/feedback-link'
            print(f'{self.command} {path}', flush=True)

        def do_GET(self):
            request = urlsplit(self.path)
            if request.path.startswith(('/f/', '/q/')):
                if not feedback_store or not public_url:
                    self.send_html(503, page('Feedback unavailable', '<h1>Feedback is not configured on this server.</h1>'))
                    return
                token = request.path.split('/')[-1]
                try:
                    snapshot = feedback_store.context(token)
                except ValueError as error:
                    self.send_html(410, page('Link expired', f'<h1>Use a fresh QR code</h1><p>{escape(str(error))}</p>'))
                    return
                if request.path.startswith('/q/'):
                    self.send_bytes(200, qr_svg(public_url + '/f/' + token), 'image/svg+xml')
                    return
                cookies = SimpleCookie()
                try:
                    cookies.load(self.headers.get('Cookie', ''))
                except CookieError:
                    pass
                browser = cookies['mountain_browser'].value if 'mountain_browser' in cookies else ''
                if len(browser) != 32 or not all(c in '0123456789abcdef' for c in browser):
                    browser = secrets.token_hex(16)
                cookie = f'mountain_browser={browser}; Path=/; HttpOnly; SameSite=Lax; Max-Age=7776000'
                if public_url.startswith('https:'):
                    cookie += '; Secure'
                self.send_html(200, form(snapshot, token, feedback_store.csrf(token, browser)), cookie)
            elif request.path in ('/assets/rainier.png', '/assets/rainier-seattle.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png', '/assets/cloud-bank.png'):
                data = (Path(__file__).resolve().parents[1] / request.path.lstrip('/')).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            elif request.path == '/health':
                self.send_json(200, {'status': 'ok'})
            elif request.path == '/api/visibility':
                try:
                    query = parse_qs(request.query)
                    location = location_from(query)
                except ValueError:
                    self.send_json(400, {'error': 'Choose mountain=rainier with viewpoint=seattle/tacoma/paradise, or mountain=hood with viewpoint=portland. Coordinate overrides are unsupported.'})
                    return
                result = service.result(location)
                if query.get('feedback', ['false'])[0].lower() == 'true':
                    result['feedback_ready'] = bool(feedback_store and public_url)
                    if result['feedback_ready']:
                        try:
                            token = feedback_store.issue(result)
                            result['feedback_qr_path'] = '/q/' + token
                        except sqlite3.Error:
                            result['feedback_ready'] = False
                self.send_json(200, result)
            else:
                self.send_json(404, {'error': 'Use /api/visibility or /health.'})

        def do_POST(self):
            if self.path != '/feedback':
                self.send_json(404, {'error': 'Not found'})
                return
            if not feedback_store or not public_url:
                self.send_html(503, page('Feedback unavailable', '<h1>Feedback is unavailable.</h1>'))
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if not 0 < length <= 4096 or self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                self.send_json(400, {'error': 'Use the feedback form; maximum request size is 4096 bytes.'})
                return
            origin = self.headers.get('Origin')
            # no-referrer can make browser POST origins opaque ("null").
            # These still require the matching session cookie and CSRF token.
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin not in (public_url, 'null')):
                self.send_json(403, {'error': 'Form origin does not match.'})
                return
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
                fields = parse_qs(self.rfile.read(length).decode(), max_num_fields=10)
                get = lambda key: fields.get(key, [''])[0]
                browser = cookies['mountain_browser'].value if 'mountain_browser' in cookies else ''
                snapshot = feedback_store.context(get('token'))
                accepted = feedback_store.submit(get('token'), browser, get('csrf'), get('answer'), get('present'))
                recent = feedback_store.recent(snapshot['mountain'], snapshot['viewpoint'])
            except (ValueError, CookieError, UnicodeError) as error:
                self.send_html(400, page('Report not saved', f'<h1>Report not saved</h1><p>{escape(str(error))}</p>'))
                return
            except sqlite3.Error:
                self.send_html(503, page('Report not saved', '<h1>Storage is temporarily unavailable.</h1><p>Please try again later.</p>'))
                return
            self.send_html(200, receipt(snapshot, get('answer'), accepted, recent))

        def send_html(self, status, content, cookie=None):
            self.send_bytes(status, content, 'text/html; charset=utf-8', cookie)

        def send_bytes(self, status, data, content_type, cookie=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, body):
            data = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--public-url', help='Public HTTPS origin; enables feedback collection.')
    parser.add_argument('--data-dir', default='.local/mountain', help='Persistent private feedback storage directory.')
    args = parser.parse_args()
    public_url = public_origin(args.public_url) if args.public_url else None
    store = FeedbackStore(args.data_dir) if public_url else None
    class Server(ThreadingHTTPServer):
        last_prune = time.monotonic()

        def service_actions(self):
            if store and time.monotonic() - self.last_prune >= 3600:
                try:
                    store.prune()
                except sqlite3.Error:
                    print('Feedback cleanup failed; inspect private storage.', flush=True)
                self.last_prune = time.monotonic()

    server = Server((args.host, args.port), handler(WeatherService(), store, public_url))
    print(f'Visibility service listening on {args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
