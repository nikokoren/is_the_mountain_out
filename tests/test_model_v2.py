import json
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch
from mountain.model import calculate, calculate_corridor
from mountain.model_v2 import calculate_v2, corridor_v2, daylight
from mountain.provider import WeatherService, fetch
from mountain.viewpoints import PARADISE, SEATTLE, samples
from test_mountain import NOW, weather


def candidate_weather(now=NOW, cloud=0, low=0, mid=0, high=0, visibility=24000, precipitation=0, code=0):
    payload = weather(cloud, visibility, precipitation, code)
    payload['hourly']['time'] = [now.timestamp()]
    for key, value in [('cloud_cover_low', low), ('cloud_cover_mid', mid), ('cloud_cover_high', high)]:
        payload['hourly'][key] = [value]
    payload['daily'] = dict(sunrise=[(NOW + timedelta(hours=-5, days=i)).timestamp() for i in (-1, 0, 1)],
                           sunset=[(NOW + timedelta(hours=5, days=i)).timestamp() for i in (-1, 0, 1)])
    return payload


class CandidateTests(unittest.TestCase):
    def test_high_cloud_is_context_without_mutating_the_control(self):
        payload = candidate_weather(cloud=100, high=100)
        control = calculate(payload, NOW, NOW, PARADISE)
        result = calculate_v2(payload, NOW, NOW, PARADISE, control)
        self.assertEqual(control['status'], 'not_out')
        self.assertEqual(control['weather_inputs']['effective_cloud_cover'], 100)
        self.assertEqual(result['status'], 'mountain_out')
        self.assertEqual(result['weather_inputs']['effective_cloud_cover'], 0)
        self.assertEqual(result['weather_inputs']['cloud_cover_high'], 100)
        self.assertEqual(result['cloud_basis'], 'low_mid_layers')

    def test_missing_layers_fall_back_and_invalid_data_stays_unknown(self):
        for missing in ('cloud_cover_low', 'cloud_cover_mid'):
            payload = candidate_weather(cloud=95, high=95)
            del payload['hourly'][missing]
            result = calculate_v2(payload, NOW, NOW, PARADISE)
            self.assertEqual(result['status'], 'not_out')
            self.assertEqual(result['cloud_basis'], 'total_cloud_fallback')
        for payload in ({}, candidate_weather(high=-1), candidate_weather(visibility=None)):
            self.assertEqual(calculate_v2(payload, NOW, NOW, PARADISE)['status'], 'unknown')

    def test_local_obstruction_limits_are_retained(self):
        for fields, status in [(dict(low=100), 'not_out'), (dict(mid=50), 'halfway_out'),
                               (dict(visibility=4999), 'not_out'), (dict(visibility=10000), 'halfway_out'),
                               (dict(precipitation=.1), 'kinda_out'), (dict(precipitation=1), 'not_out'),
                               (dict(code=45), 'not_out')]:
            with self.subTest(fields=fields):
                self.assertEqual(calculate_v2(candidate_weather(**fields), NOW, NOW, PARADISE)['status'], status)

    def test_exact_sunrise_sunset_and_night_keep_weather_separate(self):
        for hours, expected in [(-5, 'daylight'), (4.999, 'daylight'), (5, 'night'), (6, 'night')]:
            now = NOW + timedelta(hours=hours)
            result = calculate_v2(candidate_weather(now), now, now, PARADISE)
            self.assertEqual(result['observability']['state'], expected)
            self.assertEqual(result['weather_conditions']['status'], 'mountain_out')
            self.assertEqual(result['status'], 'mountain_out' if expected == 'daylight' else 'unknown')
            if expected == 'night':
                self.assertEqual(result['limiting_factors'], ['darkness'])

    def test_missing_malformed_and_unbracketed_daylight_is_unknown(self):
        valid = candidate_weather()['daily']
        invalid = [None, {}, {'sunrise': [], 'sunset': []}, {'sunrise': [True], 'sunset': [1]},
                   {'sunrise': [NOW.timestamp()], 'sunset': [NOW.timestamp() - 1]},
                   {'sunrise': [NOW.timestamp()], 'sunset': [float('nan')]},
                   {'sunrise': valid['sunrise'], 'sunset': valid['sunset'][:1]},
                   {'sunrise': [0, 1], 'sunset': [100, 101]}]
        for daily in invalid:
            payload = candidate_weather()
            payload['daily'] = daily
            result = calculate_v2(payload, NOW, NOW, PARADISE)
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['weather_conditions']['status'], 'mountain_out')
            self.assertEqual(result['limiting_factors'], ['daylight_data_unavailable'])
        payload = candidate_weather()
        payload['daily'] = {'sunrise': [NOW.timestamp() + 3600], 'sunset': [NOW.timestamp() + 7200]}
        self.assertEqual(daylight(payload, NOW)['state'], 'unknown')
        old = NOW + timedelta(days=10)
        self.assertEqual(daylight(candidate_weather(), old)['state'], 'unknown')

    def test_corridor_removes_only_the_extra_distance_cap(self):
        points = samples(SEATTLE)
        payload = candidate_weather()
        v1 = [calculate(payload, NOW, NOW, SEATTLE) for _ in points]
        v2 = [calculate_v2(payload, NOW, NOW, SEATTLE) for _ in points]
        control = calculate_corridor(v1, points, NOW, SEATTLE)
        candidate = corridor_v2(v2, points, NOW, SEATTLE)
        self.assertEqual(control['status'], 'kinda_out')
        self.assertEqual(candidate['status'], 'mountain_out')
        self.assertEqual(candidate['haze_index'], control['haze_index'])
        self.assertEqual(candidate['limiting_factors'], [])
        v2[2] = calculate_v2(candidate_weather(precipitation=2), NOW, NOW, SEATTLE)
        self.assertEqual(corridor_v2(v2, points, NOW, SEATTLE)['status'], 'not_out')
        v2[2] = calculate_v2({}, NOW, NOW, SEATTLE)
        self.assertEqual(corridor_v2(v2, points, NOW, SEATTLE)['status'], 'unknown')

    def test_corridor_daylight_is_at_the_observer_and_rechecked_at_evaluation(self):
        points = samples(SEATTLE)
        results = [calculate_v2(candidate_weather(), NOW, NOW, SEATTLE) for _ in points]
        remote = candidate_weather()
        remote.pop('daily')
        results[2] = calculate_v2(remote, NOW, NOW, SEATTLE)
        self.assertEqual(corridor_v2(results, points, NOW, SEATTLE)['status'], 'mountain_out')
        self.assertEqual(corridor_v2(results, points, NOW + timedelta(hours=2), SEATTLE)['status'], 'unknown')
        now = [NOW + timedelta(hours=5, seconds=-5)]
        def crossing(*_):
            now[0] += timedelta(seconds=3)
            return candidate_weather(now[0])
        result = WeatherService(crossing, lambda: now[0]).result(SEATTLE)
        self.assertEqual(result['status'], 'kinda_out')
        self.assertEqual(result['model_comparison']['v2']['status'], 'unknown')
        self.assertEqual(result['model_comparison']['v2']['observability']['state'], 'night')

    def test_service_evaluates_both_models_from_one_cached_fetch_per_point(self):
        calls = []
        def fetcher(*coords):
            calls.append(coords)
            return candidate_weather()
        service = WeatherService(fetcher, lambda: NOW)
        result = service.result(SEATTLE)
        comparison = result['model_comparison']
        self.assertEqual(comparison['active_model'], 'v1')
        self.assertEqual(comparison['v1']['status'], result['status'])
        self.assertEqual(comparison['v2']['status'], 'mountain_out')
        self.assertFalse(comparison['agrees'])
        service.result(SEATTLE)
        self.assertEqual(len(calls), 4)
        json.dumps(result, allow_nan=False)

    def test_sunrise_sunset_query_preserves_absolute_hour_timestamps(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(candidate_weather()).encode()
        with patch('mountain.provider.urlopen', return_value=response) as request:
            fetch(47, -122)
        params = parse_qs(urlsplit(request.call_args.args[0]).query)
        self.assertEqual(params['daily'], ['sunrise,sunset'])
        self.assertEqual(params['past_days'], ['1'])
        self.assertEqual(params['timezone'], ['UTC'])
        self.assertEqual(params['timeformat'], ['unixtime'])

    def test_v2_selection_preserves_both_models_and_local_visibility_limits(self):
        calls = []
        def fetcher(*coords):
            calls.append(coords)
            return candidate_weather(cloud=100, high=100)
        service = WeatherService(fetcher, lambda: NOW, active_model='v2')
        result = service.result(SEATTLE)
        self.assertEqual(result['status'], 'mountain_out')
        comparison = result['model_comparison']
        self.assertEqual(comparison['active_model'], 'v2')
        self.assertEqual(comparison['v1']['status'], 'not_out')
        self.assertEqual(comparison['v1']['corridor_samples'][0]['weather_inputs']['effective_cloud_cover'], 100)
        self.assertEqual(comparison['v2']['corridor_samples'][0]['weather_inputs']['effective_cloud_cover'], 0)
        service.active_model = 'v1'
        self.assertEqual(service.result(SEATTLE)['status'], 'not_out')
        self.assertEqual(len(calls), 4)
        capped = WeatherService(lambda *_: candidate_weather(visibility=19600), lambda: NOW,
                                active_model='v2').result(SEATTLE)
        self.assertEqual(capped['status'], 'halfway_out')
        with self.assertRaises(ValueError):
            WeatherService(active_model='invalid')
        json.dumps(result, allow_nan=False)
