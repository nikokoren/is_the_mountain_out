"""Open-Meteo adapter and bounded, per-coordinate cache with failure backoff."""
import json
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen
from mountain.model import calculate, calculate_corridor, unknown
from mountain.viewpoints import SEATTLE, samples

DEFAULT_LOCATION = SEATTLE
HOURLY = 'cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,precipitation,weather_code'


def fetch(latitude, longitude):
    query = urlencode(dict(latitude=latitude, longitude=longitude, hourly=HOURLY,
                           timezone='UTC', timeformat='unixtime', forecast_days=2))
    with urlopen('https://api.open-meteo.com/v1/forecast?' + query, timeout=12) as response:
        return json.load(response)


class WeatherService:
    def __init__(self, fetcher=fetch, clock=lambda: datetime.now(timezone.utc)):
        self.fetcher, self.clock = fetcher, clock
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def _sample(self, location):
        key = (location['latitude'], location['longitude'])
        # Serialize fetches to avoid duplicate upstream calls on simultaneous refreshes.
        with self.lock:
            now = self.clock()
            entry = self.cache.get(key)
            ttl = 900 if entry and entry[0] is not None else 60
            if not entry or not 0 <= (now - entry[1]).total_seconds() < ttl:
                try:
                    payload = self.fetcher(*key)
                except (OSError, ValueError, TimeoutError):
                    payload = None
                entry = (payload, self.clock())
                self.cache[key] = entry
                self.cache.move_to_end(key)
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            payload, fetched_at = entry
            now = self.clock()
        if payload is None:
            result = unknown('Weather provider unavailable. No current estimate.', now, location)
        else:
            result = calculate(payload, now, fetched_at, location)
        return result

    def result(self, location):
        if location.get('id') in ('seattle', 'tacoma', 'portland'):
            points = samples(location)
            results = [self._sample(dict(name=location['name'], latitude=lat, longitude=lon))
                       for lat, lon in points]
            result = calculate_corridor(results, points, self.clock(), location)
        else:
            result = self._sample(location)
            result['model'] = 'local-weather-v1-uncalibrated'
        result['mountain'] = location.get('mountain', 'rainier')
        result['image_path'] = location.get('image_path', '/assets/rainier.png')
        result['viewpoint'] = location.get('id', 'paradise')
        # Ready-to-display strings avoid relying on TRMNL's server timezone.
        from zoneinfo import ZoneInfo
        local = ZoneInfo('America/Los_Angeles')
        for field in ('checked_at', 'fetched_at', 'forecast_at'):
            value = result[field]
            result[field + '_label'] = datetime.fromisoformat(value).astimezone(local).strftime('%b %d %H:%M %Z') if value else 'Unavailable'
        return result
