import http.cookiejar
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer
from mountain.feedback import FeedbackStore, CONTEXT_TTL, RETENTION, public_origin, qr_svg
from mountain.provider import WeatherService
from mountain.server import handler
from mountain.viewpoints import SEATTLE
from test_mountain import NOW, weather


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = [NOW.timestamp()]
        self.store = FeedbackStore(self.directory.name, lambda: self.now[0])
        self.snapshot = WeatherService(lambda *_: weather(visibility=120000), lambda: NOW).result(SEATTLE)

    def tearDown(self):
        self.directory.cleanup()

    def test_snapshot_immutable_and_export_private(self):
        token = self.store.issue(self.snapshot)
        self.snapshot['status'] = 'not_out'
        self.assertEqual(self.store.context(token)['status'], 'mountain_out')
        browser = 'a' * 32
        self.assertTrue(self.store.submit(token, browser, self.store.csrf(token, browser), 'partial', 'yes'))
        report = list(self.store.export())[0]
        self.assertEqual(report['answer'], 'partial')
        self.assertFalse(report['verified'])
        self.assertNotIn('browser_hash', report)
        self.assertEqual(report['snapshot']['status'], 'mountain_out')
        reopened = FeedbackStore(self.directory.name, lambda: self.now[0])
        self.assertEqual(reopened.csrf(token, browser), self.store.csrf(token, browser))

    def test_duplicate_suppression_across_new_contexts(self):
        browser = 'b' * 32
        for index in range(2):
            token = self.store.issue(self.snapshot)
            self.assertEqual(self.store.submit(token, browser, self.store.csrf(token, browser), 'out', 'yes'), index == 0)
        self.assertEqual(len(list(self.store.export())), 1)

    def test_expiry_tampering_csrf_and_attestation(self):
        token = self.store.issue(self.snapshot)
        for args in [(token, 'c' * 32, 'wrong', 'out', 'yes'),
                     (token, 'c' * 32, 'é' * 64, 'out', 'yes'),
                     (token, '', '', 'out', 'yes')]:
            with self.assertRaises(ValueError):
                self.store.submit(*args)
        csrf = self.store.csrf(token, 'c' * 32)
        for answer, present in [('fake', 'yes'), ('out', '')]:
            with self.assertRaises(ValueError):
                self.store.submit(token, 'c' * 32, csrf, answer, present)
        with self.assertRaises(ValueError):
            self.store.context('z' * 24)
        self.now[0] += CONTEXT_TTL + 1
        with self.assertRaises(ValueError):
            self.store.context(token)

    def test_recent_reports_and_disagreement_review(self):
        for browser, answer in [('a' * 32, 'out'), ('b' * 32, 'partial'), ('c' * 32, 'unsure')]:
            token = self.store.issue(self.snapshot)
            self.store.submit(token, browser, self.store.csrf(token, browser), answer, 'yes')
        self.assertEqual(self.store.recent('rainier', 'seattle'), {'out': 1, 'partial': 1, 'unsure': 1})
        self.assertEqual(self.store.recent('rainier', 'tacoma'), {})
        review = list(self.store.review())
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]['answer'], 'partial')
        self.now[0] += 1201
        self.assertEqual(self.store.recent('rainier', 'seattle'), {})

    def test_retention(self):
        token = self.store.issue(self.snapshot)
        browser = 'd' * 32
        self.store.submit(token, browser, self.store.csrf(token, browser), 'unsure', 'yes')
        self.now[0] += RETENTION + 1
        self.store.prune()
        self.assertEqual(list(self.store.export()), [])

    def test_origin_validation_and_qr_encoding(self):
        self.assertEqual(public_origin('https://mountain.example/'), 'https://mountain.example')
        for url in ['http://public.example', 'https://user:password@example.com', 'https://example.com/path', 'javascript:alert(1)']:
            with self.assertRaises(ValueError):
                public_origin(url)
        svg = qr_svg('https://mountain.example/f/' + 'a' * 24)
        self.assertIn(b'<svg', svg)
        self.assertIn(b'<path', svg)


class FeedbackHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = FeedbackStore(self.directory.name)
        self.service = WeatherService(lambda *_: weather(visibility=120000), lambda: NOW)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.service, self.store, 'http://127.0.0.1'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'
        self.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def get(self, path):
        return self.client.open(self.root + path)

    def test_opt_in_form_qr_submission_and_export_not_public(self):
        plain = json.load(self.get('/api/visibility'))
        self.assertNotIn('feedback_qr_path', plain)
        shown = json.load(self.get('/api/visibility?feedback=true'))
        self.assertTrue(shown['feedback_ready'])
        qr = self.get(shown['feedback_qr_path'])
        self.assertEqual(qr.headers['Content-Type'], 'image/svg+xml')
        token = shown['feedback_qr_path'].split('/')[-1]
        response = self.get('/f/' + token)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        html = response.read().decode()
        self.assertIn('Kerry Park', html)
        self.assertNotIn('MOUNTAIN OUT!', html)
        csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        data = urlencode(dict(token=token, csrf=csrf, answer='out', present='yes', status='not_out')).encode()
        response = self.client.open(Request(self.root + '/feedback', data=data))
        receipt = response.read()
        self.assertIn(b'observation was saved', receipt)
        self.assertIn(b'agrees with', receipt)
        self.assertIn(b'Recent reports', receipt)
        report = list(self.store.export())[0]
        self.assertEqual(report['snapshot']['status'], 'mountain_out')
        self.assertEqual(json.load(self.get('/api/visibility'))['status'], plain['status'])
        with self.assertRaises(HTTPError) as error:
            self.get('/api/feedback')
        self.assertEqual(error.exception.code, 404)

    def test_invalid_forms_and_stale_links(self):
        for body, headers in [(b'x' * 5000, {'Content-Type': 'application/x-www-form-urlencoded'}),
                              (b'{}', {'Content-Type': 'application/json'}),
                              (b'token=bad', {'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://evil.example'})]:
            with self.assertRaises(HTTPError) as error:
                self.client.open(Request(self.root + '/feedback', data=body, headers=headers))
            self.assertIn(error.exception.code, (400, 403))
        with self.assertRaises(HTTPError) as error:
            self.get('/f/' + 'x' * 24)
        self.assertEqual(error.exception.code, 410)
        self.assertEqual(list(self.store.export()), [])

    def test_unconfigured_feedback_does_not_break_weather(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            data = json.load(self.client.open(f'http://127.0.0.1:{server.server_port}/api/visibility?feedback=true'))
            self.assertFalse(data['feedback_ready'])
            self.assertNotIn('feedback_qr_path', data)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
