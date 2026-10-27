import unittest
from datetime import timedelta
from mountain.provider import WeatherService
from mountain.viewpoints import SEATTLE, PARADISE, samples, distance
from mountain.server import location_from
from test_mountain import weather, NOW


class SeattleTests(unittest.TestCase):
    def test_default_and_geometry(self):
        self.assertEqual(location_from({}), SEATTLE)
        self.assertEqual(location_from({'viewpoint': ['paradise']}), PARADISE)
        with self.assertRaises(ValueError):
            location_from({'viewpoint': ['sunrise']})
        points = samples(SEATTLE)
        self.assertEqual(len(points), 4)
        self.assertTrue(85000 < distance(points[0], points[-1]) < 105000)

    def test_corridor_cache_and_image(self):
        calls = []
        def fetch(*coords):
            calls.append(coords)
            return weather(visibility=120000)
        service = WeatherService(fetch, lambda: NOW)
        result = service.result(SEATTLE)
        self.assertEqual(result['status'], 'mountain_out')
        self.assertEqual(result['image_path'], '/assets/rainier-seattle.png')
        self.assertEqual(len(result['corridor_samples']), 4)
        service.result(SEATTLE)
        self.assertEqual(len(calls), 4)
        self.assertEqual(service.result(PARADISE)['image_path'], '/assets/rainier.png')

    def test_clear_observer_cloudy_corridor(self):
        points = samples(SEATTLE)
        service = WeatherService(lambda *p: weather(cloud=100 if p == points[2] else 0, visibility=120000), lambda: NOW)
        self.assertEqual(service.result(SEATTLE)['status'], 'not_out')

    def test_missing_and_stale_remote_sample(self):
        for payload in ({}, {'hourly': {'time': [(NOW - timedelta(hours=3)).timestamp()]}}):
            service = WeatherService(lambda lat, lon: payload if lat < 47 else weather(), lambda: NOW)
            self.assertEqual(service.result(SEATTLE)['status'], 'unknown')

    def test_distance_penalty_differs_from_local(self):
        service = WeatherService(lambda *_: weather(visibility=30000), lambda: NOW)
        self.assertEqual(service.result(PARADISE)['status'], 'mountain_out')
        self.assertEqual(service.result(SEATTLE)['status'], 'halfway_out')

    def test_visibility_and_precipitation_along_corridor(self):
        points = samples(SEATTLE)
        for remote in (weather(visibility=1000), weather(precipitation=2)):
            service = WeatherService(lambda *p: remote if p == points[-1] else weather(visibility=120000), lambda: NOW)
            self.assertEqual(service.result(SEATTLE)['status'], 'not_out')
