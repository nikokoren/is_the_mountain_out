"""Run: python -m mountain.server. Put a TLS reverse proxy in front for TRMNL polling."""
import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from mountain.provider import WeatherService


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



def handler(service):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlsplit(self.path)
            if request.path in ('/assets/rainier.png', '/assets/rainier-seattle.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png', '/assets/cloud-bank.png'):
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
                    location = location_from(parse_qs(request.query))
                except ValueError:
                    self.send_json(400, {'error': 'Choose mountain=rainier with viewpoint=seattle/tacoma/paradise, or mountain=hood with viewpoint=portland. Coordinate overrides are unsupported.'})
                    return
                self.send_json(200, service.result(location))
            else:
                self.send_json(404, {'error': 'Use /api/visibility or /health.'})

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
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler(WeatherService()))
    print(f'Visibility service listening on {args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
