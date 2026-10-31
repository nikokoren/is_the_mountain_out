"""Validate native responsive layout, text fitting and QR decoding across devices."""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from PIL import Image
import zxingcpp
from tools.preview import STATES, SIZES, render
from tools.browser_support import install_assets, settle

ROOT = Path(__file__).resolve().parents[1]
DEVICES = [(None, 800, 480), ('v2', 1872, 1404), ('amazon_kindle_7', 800, 600),
           ('palma', 1648, 824), ('kobo_forma', 1920, 1440)]
URL = 'https://mountain.example.com/f/0123456789abcdef01234567'
IMAGES = ['/assets/rainier-seattle.png', '/assets/rainier.png', '/assets/rainier-tacoma.png', '/assets/hood-portland.png']


def main():
    count = scans = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        install_assets(page)
        for device, width, height in DEVICES:
            for portrait in (False, True):
                page.set_viewport_size({'width': height if portrait else width, 'height': width if portrait else height})
                for layout in SIZES:
                    for feedback in (False, True):
                        # All artwork/states on the original screen; longest verdict and
                        # unknown and fully clouded on every other device/orientation/view/QR combination.
                        images = IMAGES if device is None and not portrait else IMAGES[:1]
                        states = STATES if device is None and not portrait else ['mountain_out', 'unknown', 'not_out']
                        for image_path in images:
                            for state in states:
                                case = (device, portrait, layout, feedback, image_path, state)
                                page.set_content(render(state, layout, device=device, portrait=portrait,
                                                        image_path=image_path, feedback_url=URL if feedback else None, feedback_qr_path='/q/0123456789abcdef01234567' if feedback else None))
                                settle(page)
                                bounds = page.locator('.screen').bounding_box()
                                assert round(bounds['width']) == (height if portrait else width), case
                                assert round(bounds['height']) == (width if portrait else height), case
                                actual = page.locator('.value').inner_text()
                                assert actual == ('UNKNOWN' if state == 'unknown' else ['NOT OUT','KINDA OUT','HALFWAY OUT','MOSTLY OUT','MOUNTAIN OUT!'][STATES.index(state)]), case
                                metrics = page.locator('.view').evaluate("""view => {
                                  const outer=view.getBoundingClientRect();
                                  const nodes=Array.from(view.querySelectorAll('div,.value,svg'));
                                  return nodes.filter(n=>!n.closest('svg')||n.tagName==='svg').map(n=>{
                                    const b=n.getBoundingClientRect();return {class:n.getAttribute('class'),x:b.x-outer.x,y:b.y-outer.y,w:b.width,h:b.height,
                                      font:n.classList.contains('value')?parseFloat(getComputedStyle(n).fontSize):null};});
                                }""")
                                view = page.locator('.view').bounding_box()
                                content = page.locator('.layout > div').bounding_box()
                                mountain = page.locator('[data-mountain-region]').bounding_box()
                                verdict = page.locator('[data-verdict-region]').bounding_box()
                                text = page.locator('.value').bounding_box()
                                assert abs(mountain['height'] / content['height'] - .52) < .005, case
                                gap = verdict['y'] - mountain['y'] - mountain['height']
                                assert 0 < gap <= content['height'] * .05, (case, gap)
                                assert abs(text['y'] - verdict['y']) < 1, case
                                assert abs(text['x'] + text['width']/2 - content['x'] - content['width']/2) < 1, case
                                assert page.locator('[data-mountain-region] > svg').get_attribute('preserveAspectRatio') == 'xMidYMax meet', case
                                for item in metrics:
                                    assert item['x'] >= -1 and item['y'] >= -1 and item['x']+item['w'] <= view['width']+1 and item['y']+item['h'] <= view['height']+1, (case,item,view)
                                    if item['font'] is not None: assert item['font'] >= 12, (case,item)
                                assert page.locator('svg.qr-code').count() == int(feedback and layout == 'full'), case
                                if feedback and layout == 'full':
                                    qr = page.locator('[data-feedback-qr] > .p--3')
                                    decoded = zxingcpp.read_barcode(Image.open(io.BytesIO(qr.screenshot())))
                                    assert decoded and decoded.text == URL, (case, 'QR did not decode')
                                    anchor=page.locator('[data-feedback-qr]').bounding_box()
                                    # View bounds alone miss text hidden behind an
                                    # opaque QR. Check the actual text glyph range.
                                    glyphs=page.locator('.value').evaluate("""el => {
                                      const range=document.createRange();range.selectNodeContents(el);
                                      const r=range.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};
                                    }""")
                                    overlap_x=min(glyphs['x']+glyphs['w'],anchor['x']+anchor['width'])-max(glyphs['x'],anchor['x'])
                                    overlap_y=min(glyphs['y']+glyphs['h'],anchor['y']+anchor['height'])-max(glyphs['y'],anchor['y'])
                                    assert overlap_x <= 1 or overlap_y <= 1, (case, 'Verdict hidden by QR', glyphs, anchor)
                                    assert abs(text['y'] - anchor['y']) < 1, (case, text, anchor)
                                    # Approximate one-inch square including the quiet zone:
                                    # OG ~125 ppi; X ~176 ppi, with native 1.8x scaling.
                                    if device is None or device == 'v2':
                                        expected_width = 128 if device is None else 96 * 1.8
                                        assert abs(anchor['width'] - expected_width) <= 1, (case, anchor)
                                    content=page.locator('.layout > div').bounding_box()
                                    assert abs(anchor['x']+anchor['width']-content['x']-content['width'])<=1, case
                                    assert abs(anchor['y']+anchor['height']-content['y']-content['height'])<=1, case
                                    assert page.locator('[data-feedback-qr] .label').inner_text()=='Submit report', case
                                    scans += 1
                                count += 1
        for feedback, filename in [(False,'clear-fixture.png'),(True,'feedback-qr-preview.png'),(True,'not-out-qr-preview.png')]:
            page.set_viewport_size({'width':800,'height':480})
            page.set_content(render(state='not_out' if filename.startswith('not-out') else 'mountain_out', feedback_url=URL if feedback else None, feedback_qr_path='/q/0123456789abcdef01234567' if feedback else None))
            settle(page)
            page.locator('.screen').screenshot(path=str(ROOT/'docs'/filename))
        browser.close()
    print(f'{count} responsive layout checks and {scans} decoded QR screenshots passed across 5 devices, both orientations and all four views; native Framework 3.4.0 CSS/JS/fonts.')


if __name__ == '__main__':
    main()
