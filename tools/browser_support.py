"""Load unmodified Framework 3.4.0 CSS, JS and fonts in the local harness."""
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def install_assets(page):
    def asset(route):
        path = urlsplit(route.request.url).path
        if path == '/css/3.4.0/plugins.css':
            route.fulfill(path=str(ROOT / '.venv/framework/plugins.css'), content_type='text/css')
        elif path == '/js/3.4.0/plugins.js':
            route.fulfill(path=str(ROOT / '.venv/framework/plugins.js'), content_type='application/javascript')
        elif path.startswith('/fonts/'):
            route.fulfill(path=str(ROOT / '.venv/framework' / path.lstrip('/')))
        elif path in ('/assets/rainier.png', '/assets/rainier-seattle.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png', '/assets/cloud-bank.png'):
            route.fulfill(path=str(ROOT / path.lstrip('/')), content_type='image/png')
        else:
            # In particular, native inline QR rendering must never request /q/.
            route.abort()
    page.route('**/*', asset)


def settle(page):
    page.evaluate('document.fonts.ready')
    page.evaluate('window.terminalize()')
    page.wait_for_function('window.TRMNL_PLUGINS_READY === true')
