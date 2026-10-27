import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from mountain.viewpoints import TACOMA, SEATTLE, samples, distance
from mountain.provider import WeatherService
from mountain.server import location_from, handler
from test_mountain import weather, NOW


class TacomaTests(unittest.TestCase):
    def test_preset_and_corridor(self):
        self.assertEqual(location_from({'viewpoint': ['tacoma']}), TACOMA)
        points = samples(TACOMA)
        self.assertEqual(len(points), 4)
        self.assertNotEqual(points[0], samples(SEATTLE)[0])
        self.assertTrue(65000 < distance(points[0], points[-1]) < 80000)

    def test_distance_sensitive_model_cache_and_image(self):
        calls = []
        def fetch(*coords):
            calls.append(coords)
            return weather(visibility=40000)
        service = WeatherService(fetch, lambda: NOW)
        result = service.result(TACOMA)
        self.assertEqual(result['status'], 'mostly_out')
        self.assertEqual(result['viewpoint'], 'tacoma')
        self.assertEqual(result['image_path'], '/assets/rainier-tacoma.png')
        self.assertEqual(result['model'], 'tacoma-corridor-v1-uncalibrated')
        self.assertEqual(len(result['corridor_samples']), 4)
        service.result(TACOMA)
        self.assertEqual(len(calls), 4)
        self.assertEqual(service.result(SEATTLE)['status'], 'halfway_out')

    def test_remote_failure_and_cloud(self):
        for remote, expected in [({}, 'unknown'), (weather(cloud=100), 'not_out')]:
            end = samples(TACOMA)[-1]
            service = WeatherService(lambda *p: remote if p == end else weather(visibility=120000), lambda: NOW)
            result = service.result(TACOMA)
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['image_path'], '/assets/rainier-tacoma.png')

    def test_http_preset_and_artwork(self):
        service = WeatherService(lambda *_: weather(visibility=120000), lambda: NOW)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(root + '/api/visibility?viewpoint=tacoma') as response:
                data = json.load(response)
            self.assertEqual(data['viewpoint'], 'tacoma')
            self.assertEqual(data['status'], 'mountain_out')
            with urlopen(root + data['image_path']) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertTrue(response.read().startswith(b'\x89PNG'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
