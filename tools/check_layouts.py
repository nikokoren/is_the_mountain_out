"""Check every fixture in system Chromium; no external requests needed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from tools.preview import SIZES, STATES, render


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                    args=['--no-sandbox'])
        page = browser.new_page()
        def asset(route):
            from urllib.parse import urlsplit
            path = urlsplit(route.request.url).path
            if path == '/css/3.4.0/plugins.css':
                route.fulfill(path=str(Path('.venv/framework/plugins.css').resolve()), content_type='text/css')
            elif path.startswith('/fonts/'):
                route.fulfill(path=str((Path('.venv/framework') / path.lstrip('/')).resolve()))
            elif path in ('/assets/rainier.png', '/assets/rainier-seattle.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png', '/assets/cloud-bank.png'):
                route.fulfill(path=str(Path(path.lstrip('/')).resolve()), content_type='image/png')
            else:
                route.abort()
        page.route('**/*', asset)
        for image_path in ('/assets/rainier-seattle.png', '/assets/rainier.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png'):
            for layout, (width, height) in SIZES.items():
                page.set_viewport_size({'width': 800, 'height': 480})
                for state in STATES:
                    page.set_content(render(state, layout, image_path=image_path))
                    page.evaluate('document.fonts.ready')
                    assert page.locator('.view').inner_text().strip() == ('UNKNOWN' if state == 'unknown' else ['NOT OUT', 'KINDA OUT', 'HALFWAY OUT', 'MOSTLY OUT', 'MOUNTAIN OUT!'][STATES.index(state)])
                    for element in page.locator('.layout > *').all():
                        box = element.bounding_box()
                        view = page.locator('.view').bounding_box()
                        assert box['x'] >= view['x'] and box['y'] >= view['y'], (layout, state, box)
                        assert box['x'] + box['width'] <= view['x'] + view['width'] + 1, (layout, state, box)
                        assert box['y'] + box['height'] <= view['y'] + view['height'] + 1, (layout, state, box)
                    dimensions = page.evaluate('''() => {
                      const r = document.querySelector('.layout');
                      return {height:r.scrollHeight, allowed:r.clientHeight,
                              width:r.scrollWidth, allowedWidth:r.clientWidth,
                              svg:document.querySelector('svg').getBoundingClientRect().height};
                    }''')
                    assert dimensions['height'] <= dimensions['allowed'], (layout, state, dimensions)
                    assert dimensions['width'] <= dimensions['allowedWidth'], (layout, state, dimensions)
                    assert dimensions['svg'] >= 30, (layout, state, dimensions)
        page.set_content(render('mountain_out', 'full'))
        page.evaluate('document.fonts.ready')
        page.locator('.screen').screenshot(path='docs/clear-fixture.png')
        browser.close()
    print('96 browser layout checks passed (official Framework 3.4.0 CSS and fonts; local Liquid harness).')


if __name__ == '__main__':
    main()
