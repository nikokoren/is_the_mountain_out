import json
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
import yaml
from liquid import Environment
from mountain.viewpoints import PORTLAND, MOUNTAINS, samples, distance
from mountain.provider import WeatherService
from mountain.server import location_from, handler
from test_mountain import weather, NOW


class HoodTests(unittest.TestCase):
    def test_target_and_pair_validation(self):
        self.assertEqual(location_from({'mountain': ['hood']}), PORTLAND)
        points = samples(PORTLAND)
        self.assertEqual(points[-1], MOUNTAINS['hood']['summit'])
        self.assertTrue(75000 < distance(points[0], points[-1]) < 85000)
        for query in ({'mountain': ['hood'], 'viewpoint': ['seattle']},
                      {'mountain': ['rainier'], 'viewpoint': ['portland']},
                      {'mountain': ['other']}):
            with self.assertRaises(ValueError):
                location_from(query)

    def test_weather_routing_and_failure(self):
        calls = []
        def fetch(*point):
            calls.append(point)
            return weather(visibility=120000)
        service = WeatherService(fetch, lambda: NOW)
        result = service.result(PORTLAND)
        self.assertEqual(result['mountain'], 'hood')
        self.assertEqual(result['status'], 'mountain_out')
        self.assertEqual(result['image_path'], '/assets/hood-portland.png')
        self.assertIn('Mount Hood', result['explanation'])
        self.assertEqual(calls[-1], MOUNTAINS['hood']['summit'])
        service.result(PORTLAND)
        self.assertEqual(len(calls), 4)
        failed = WeatherService(lambda *_: {}, lambda: NOW).result(PORTLAND)
        self.assertEqual(failed['status'], 'unknown')
        self.assertEqual(failed['mountain'], 'hood')

    def test_native_conditions_and_active_polling_field(self):
        settings = yaml.safe_load(Path('plugin/src/settings.yml').read_text())
        fields = {f['keyname']: f for f in settings['custom_fields']}
        rules = {r['when']: r for r in fields['mountain']['conditional_validation']}
        self.assertEqual(rules['rainier']['hidden'], ['hood_viewpoint'])
        self.assertEqual(rules['hood']['hidden'], ['rainier_viewpoint'])
        template = Environment().from_string(settings['polling_url'])
        params = dict(mountain='hood',
                      rainier_viewpoint='tacoma', hood_viewpoint='portland')
        self.assertEqual(template.render(**params), 'https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev/api/visibility?mountain=hood&viewpoint=portland&feedback=false')
        params['mountain'] = 'rainier'
        self.assertTrue(template.render(**params).endswith('mountain=rainier&viewpoint=tacoma&feedback=false'))
        self.assertTrue(template.render().endswith('mountain=rainier&viewpoint=seattle&feedback=false'))

    def test_http_target_image_and_mismatched_selection(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(WeatherService(lambda *_: weather(visibility=120000), lambda: NOW)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(root + '/api/visibility?mountain=hood&viewpoint=portland') as response:
                data = json.load(response)
            self.assertEqual(data['mountain'], 'hood')
            with urlopen(root + data['image_path']) as response:
                self.assertTrue(response.read().startswith(b'\x89PNG'))
            with self.assertRaises(HTTPError) as error:
                urlopen(root + '/api/visibility?mountain=hood&viewpoint=tacoma')
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
