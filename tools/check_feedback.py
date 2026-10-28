"""Exercise the mobile feedback flow against controlled weather and temporary storage."""
import json
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from mountain.feedback import FeedbackStore
from mountain.provider import WeatherService
from mountain.server import handler


def main():
    now = datetime.now(timezone.utc)

    def weather(*_):
        return {'hourly': {'time': [now.timestamp()], 'cloud_cover': [0],
                           'visibility': [120000], 'precipitation': [0], 'weather_code': [0]}}

    with tempfile.TemporaryDirectory() as directory:
        store = FeedbackStore(directory)
        server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        root = f'http://127.0.0.1:{server.server_port}'
        server.RequestHandlerClass = handler(WeatherService(weather), store, root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(root + '/api/visibility?mountain=hood&viewpoint=portland&feedback=true') as response:
                result = json.load(response)
            token = result['feedback_qr_path'].split('/')[-1]
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 390, 'height': 844})
                page.goto(root + '/f/' + token)
                assert page.locator('h1').inner_text() == 'Is Mount Hood / Wy’east out right now?'
                assert page.evaluate('document.documentElement.scrollWidth') == 390
                page.screenshot(path='docs/feedback-form-preview.png', full_page=True)
                page.locator('input[value="partial"]').check()
                page.locator('input[name="present"]').check()
                page.get_by_role('button', name='Send observation').click()
                page.get_by_text('Your observation was saved. Thank you.').wait_for()
                page.get_by_text('Your observation differs from the weather estimate.', exact=False).wait_for()
                page.screenshot(path='docs/feedback-receipt-preview.png', full_page=True)
                report = list(store.export())[0]
                assert report['mountain'] == 'hood' and report['answer'] == 'partial'
                assert len(list(store.review())) == 1
                browser.close()
            print('Mobile form, saved observation, recent reports, and disagreement review verified.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
