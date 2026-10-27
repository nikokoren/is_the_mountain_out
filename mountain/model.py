"""Explainable, uncalibrated heuristics; never a probability or observation."""
from datetime import datetime, timezone
from math import isfinite

UTC = timezone.utc
MAX_HOUR_AGE = 5400
MAX_RESPONSE_AGE = 3600
LABELS = ['Not Out', 'Kinda Out', 'Halfway Out', 'Mostly Out', 'Mountain OUT!']


def unknown(reason, checked_at, location, fetched_at=None, forecast_at=None):
    return dict(status='unknown', verdict='UNKNOWN', explanation=reason,
                location=location, checked_at=checked_at.isoformat(),
                fetched_at=fetched_at.isoformat() if fetched_at else None,
                forecast_at=forecast_at.isoformat() if forecast_at else None,
                source='Open-Meteo', estimate=True)


def calculate(payload, now, fetched_at, location):
    """Use UTC Unix timestamps to avoid local DST ambiguity. Optional layers tighten cloud score."""
    def fail(reason, hour=None):
        return unknown(reason, now, location, fetched_at, hour)
    if not 0 <= (now - fetched_at).total_seconds() <= MAX_RESPONSE_AGE:
        return fail('Weather response is stale. Try again later.')
    try:
        hourly = payload['hourly']
        times = hourly['time']
        if not times:
            return fail('No hourly forecast available.')
        index = min(range(len(times)), key=lambda i: abs(float(times[i]) - now.timestamp()))
        hour = datetime.fromtimestamp(float(times[index]), UTC)
        if abs((now - hour).total_seconds()) > MAX_HOUR_AGE:
            return fail('No sufficiently recent forecast hour.', hour)

        def number(key, low, high, optional=False):
            values = hourly.get(key, [])
            value = values[index] if index < len(values) else None
            if value is None and optional:
                return None
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or not low <= value <= high:
                raise ValueError(key)
            return value

        cloud = number('cloud_cover', 0, 100)
        layers = [number(k, 0, 100, True) for k in
                  ('cloud_cover_low', 'cloud_cover_mid', 'cloud_cover_high')]
        cloud = max([cloud] + [v for v in layers if v is not None])
        visibility = number('visibility', 0, 1000000)
        rain = number('precipitation', 0, 1000)
        code = number('weather_code', 0, 99)
        if int(code) != code or code not in {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}:
            raise ValueError('weather_code')
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, OSError):
        return fail('Weather data is missing or invalid.')

    level = 4 if cloud <= 15 else 3 if cloud <= 35 else 2 if cloud <= 60 else 1 if cloud <= 85 else 0
    visibility_cap = 0 if visibility < 5000 else 1 if visibility < 10000 else 2 if visibility < 20000 else 4
    level = min(level, visibility_cap)
    if rain >= 1 or code in {45, 48, 65, 67, 75, 82, 86, 95, 96, 99}:
        level = 0
    elif rain > 0 or code >= 51:
        level = min(level, 1)
    explanations = [
        'Cloud, fog or precipitation makes a view unlikely.',
        'A partial view is plausible; cloud or haze may hide the mountain.',
        'Mixed conditions may reveal some of the mountain.',
        'Conditions favour a view, with some cloud possible.',
        'Clear conditions favour a view of the mountain.',
    ]
    result = fail(explanations[level], hour)
    result.update(status=['not_out', 'kinda_out', 'halfway_out', 'mostly_out', 'mountain_out'][level],
                  verdict=LABELS[level].upper(), visibility_m=visibility)
    return result


def calculate_corridor(results, points, now, location):
    """Conservative sampled weather heuristic, not terrain or atmospheric ray tracing."""
    from mountain.viewpoints import distance, MOUNTAINS
    evidence = [dict(latitude=p[0], longitude=p[1], status=r['status'],
                     forecast_at=r['forecast_at'], fetched_at=r['fetched_at'],
                     visibility_m=r.get('visibility_m')) for p, r in zip(points, results)]
    if len(results) != 4 or any(r['status'] == 'unknown' or not r['forecast_at'] or
            abs((now - datetime.fromisoformat(r['forecast_at'])).total_seconds()) > MAX_HOUR_AGE or
            not r['fetched_at'] or not 0 <= (now - datetime.fromisoformat(r['fetched_at'])).total_seconds() <= MAX_RESPONSE_AGE
            for r in results):
        result = unknown('A viewing-corridor forecast is unavailable or stale.', now, location)
    else:
        states = ['not_out', 'kinda_out', 'halfway_out', 'mostly_out', 'mountain_out']
        level = min(states.index(r['status']) for r in results)
        # Trapezoidal distance/visibility index. Surface visibility has height and
        # provider ceiling limitations; this is only a tunable haze penalty.
        burden = sum(distance(points[i], points[i+1]) *
                     (1 / max(results[i]['visibility_m'], 1) +
                      1 / max(results[i+1]['visibility_m'], 1)) / 2
                     for i in range(3))
        cap = 4 if burden <= 1 else 3 if burden <= 2 else 2 if burden <= 4 else 1 if burden <= 8 else 0
        level = min(level, cap)
        result = dict(results[0])
        result.update(status=states[level], verdict=LABELS[level].upper(), location=location,
                      forecast_at=min(r['forecast_at'] for r in results),
                      fetched_at=min(r['fetched_at'] for r in results),
                      explanation=f"Weather-only estimate from {location['name']} across the {MOUNTAINS[location.get('mountain', 'rainier')]['name']} corridor; not a confirmed view.",
                      distance_m=round(distance(points[0], points[-1])), haze_index=round(burden, 3))
    result['checked_at'] = now.isoformat()
    result['corridor_samples'] = evidence
    result['model'] = location['id'] + '-corridor-v1-uncalibrated'
    return result
