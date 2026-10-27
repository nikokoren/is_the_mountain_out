"""Capture actual recipe fixtures and build review sheets outside the display UI."""
import base64
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from tools.preview import render, STATES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/previews'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                    args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 800, 'height': 480})

        def asset(route):
            path = urlsplit(route.request.url).path
            if path == '/css/3.4.0/plugins.css':
                route.fulfill(path=str(ROOT / '.venv/framework/plugins.css'), content_type='text/css')
            elif path.startswith('/fonts/'):
                route.fulfill(path=str(ROOT / '.venv/framework' / path.lstrip('/')))
            elif path in ('/assets/rainier.png', '/assets/rainier-seattle.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png', '/assets/cloud-bank.png'):
                route.fulfill(path=str(ROOT / path.lstrip('/')), content_type='image/png')
            else:
                route.abort()

        page.route('**/*', asset)
        for viewpoint, title, image in [('seattle', 'Seattle — Kerry Park', 'rainier-seattle.png'),
                                        ('paradise', 'Paradise', 'rainier.png'),
                                        ('tacoma', 'Tacoma — Ruston Way', 'rainier-tacoma.png'),
                                        ('portland', 'Portland — Mount Hood', 'hood-portland.png')]:
            cards = []
            for state in STATES:
                page.set_viewport_size({'width': 800, 'height': 480})
                page.set_content(render(state, 'full', image_path='/assets/' + image))
                page.evaluate('document.fonts.ready')
                png = page.locator('.screen').screenshot(path=str(OUTPUT / f'{viewpoint}-{state}.png'))
                cards.append('<img width="400" height="240" src="data:image/png;base64,' +
                             base64.b64encode(png).decode() + '">')
            # Review-sheet labels and borders are outside the captured device UI.
            sheet = f'''<!doctype html><html><head><meta charset="utf-8"><style>
              body {{margin:0;padding:24px;background:#eee;font-family:Arial,sans-serif}}
              h1 {{margin:0 0 8px;font-size:26px}} p {{margin:0 0 20px;font-size:15px}}
              main {{display:grid;grid-template-columns:repeat(3,400px);gap:16px}}
              img {{display:block;border:1px solid #ccc;box-sizing:border-box;background:white}}
              </style></head><body><h1>{title}</h1>
              <p>All six states · Framework 3.4.0 · illustrative fixtures, not live weather</p>
              <main>{''.join(cards)}</main></body></html>'''
            (OUTPUT / f'{viewpoint}-states.html').write_text(sheet)
            page.set_viewport_size({'width': 1280, 'height': 610})
            page.set_content(sheet)
            page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
            page.screenshot(path=str(OUTPUT / f'{viewpoint}-states.png'), full_page=True)
        browser.close()
    print('Rendered 24 full-resolution screens and four state preview sheets in docs/previews.')


if __name__ == '__main__':
    main()
