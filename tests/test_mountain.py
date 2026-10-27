import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from mountain.model import calculate
from mountain.provider import WeatherService
from mountain.viewpoints import PARADISE as DEFAULT_LOCATION, SEATTLE
from mountain.server import handler, location_from

NOW = datetime(2026, 10, 27, 19, tzinfo=timezone.utc)


def weather(cloud=0, visibility=30000, precipitation=0, code=0):
    return {'hourly': {'time': [NOW.timestamp()], 'cloud_cover': [cloud],
                       'visibility': [visibility], 'precipitation': [precipitation], 'weather_code': [code]}}


class ModelTests(unittest.TestCase):
    def result(self, payload, now=NOW, fetched=NOW):
        return calculate(payload, now, fetched, DEFAULT_LOCATION)

    def test_cloud_states_and_boundaries(self):
        for cloud, expected in [(0, 'mountain_out'), (15, 'mountain_out'), (16, 'mostly_out'),
                                (35, 'mostly_out'), (36, 'halfway_out'), (60, 'halfway_out'),
                                (61, 'kinda_out'), (85, 'kinda_out'), (86, 'not_out'), (100, 'not_out')]:
            with self.subTest(cloud=cloud):
                self.assertEqual(self.result(weather(cloud))['status'], expected)

    def test_visibility_and_precipitation_caps(self):
        for args, expected in [({'visibility': 4999}, 'not_out'), ({'visibility': 5000}, 'kinda_out'),
                               ({'visibility': 10000}, 'halfway_out'), ({'visibility': 20000}, 'mountain_out'),
                               ({'precipitation': .1}, 'kinda_out'), ({'precipitation': 1}, 'not_out'),
                               ({'code': 45}, 'not_out'), ({'code': 95}, 'not_out'), ({'code': 71}, 'kinda_out')]:
            with self.subTest(args=args):
                self.assertEqual(self.result(weather(**args))['status'], expected)

    def test_layers_can_reduce_visibility(self):
        data = weather()
        data['hourly']['cloud_cover_high'] = [95]
        self.assertEqual(self.result(data)['status'], 'not_out')

    def test_missing_and_invalid_data(self):
        for data in [{}, {'hourly': {'time': []}}, weather(cloud=None), weather(visibility=float('nan')),
                     weather(cloud=-1), weather(code=4), weather(code=1.5), weather(cloud=True)]:
            with self.subTest(data=data):
                self.assertEqual(self.result(data)['status'], 'unknown')

    def test_stale_hour_and_response(self):
        self.assertEqual(self.result(weather(), NOW + timedelta(hours=2), NOW + timedelta(hours=2))['status'], 'unknown')
        self.assertEqual(self.result(weather(), NOW, NOW - timedelta(hours=2))['status'], 'unknown')
        self.assertEqual(self.result(weather(), NOW, NOW + timedelta(minutes=1))['status'], 'unknown')

    def test_nearest_hour_uses_absolute_time(self):
        data = weather()
        data['hourly'] = {key: [val[0], val[0]] for key, val in data['hourly'].items()}
        data['hourly']['time'] = [(NOW - timedelta(hours=1)).timestamp(), NOW.timestamp()]
        data['hourly']['cloud_cover'] = [100, 0]
        self.assertEqual(self.result(data)['status'], 'mountain_out')


class ServiceTests(unittest.TestCase):
    def test_cache_coordinates_labels_and_expiry(self):
        now = [NOW]
        calls = []
        def fetch(*coords):
            calls.append(coords)
            return weather()
        service = WeatherService(fetch, lambda: now[0])
        first = service.result(DEFAULT_LOCATION)
        renamed = dict(DEFAULT_LOCATION, name='Another label')
        self.assertEqual(service.result(renamed)['location']['name'], 'Another label')
        self.assertEqual(len(calls), 1)
        self.assertIn('PDT', first['forecast_at_label'])
        now[0] += timedelta(minutes=16)
        service.result(DEFAULT_LOCATION)
        service.result(dict(DEFAULT_LOCATION, latitude=47))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][0], 47)

    def test_failure_backoff_and_recovery(self):
        now, calls = [NOW], []
        def fetch(*_):
            calls.append(1)
            if len(calls) == 1:
                raise OSError('offline')
            return weather()
        service = WeatherService(fetch, lambda: now[0])
        self.assertEqual(service.result(DEFAULT_LOCATION)['status'], 'unknown')
        service.result(DEFAULT_LOCATION)
        self.assertEqual(len(calls), 1)
        now[0] += timedelta(seconds=61)
        self.assertEqual(service.result(DEFAULT_LOCATION)['status'], 'mountain_out')

    def test_configuration_validation(self):
        self.assertEqual(location_from({}), SEATTLE)
        self.assertEqual(location_from({'viewpoint': ['paradise']}), DEFAULT_LOCATION)
        for value in ['nan', 'inf', '91', 'abc']:
            with self.assertRaises(ValueError):
                location_from({'latitude': [value]})

    def test_http_functional_request(self):
        service = WeatherService(lambda *_: weather(), lambda: NOW)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(root + '/api/visibility?viewpoint=paradise') as response:
                result = json.load(response)
            self.assertEqual(result['status'], 'mountain_out')
            self.assertEqual(result['location']['latitude'], 46.786)
            self.assertEqual(result['location']['name'], 'Paradise')
            with self.assertRaises(HTTPError) as error:
                urlopen(root + '/api/visibility?latitude=nan')
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
