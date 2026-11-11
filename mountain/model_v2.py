"""Experimental model: layer-aware weather, no distance cap, explicit daylight."""
from datetime import datetime
from math import isfinite
from mountain.model import calculate, calculate_corridor, LABELS, UTC

STATES = ['not_out', 'kinda_out', 'halfway_out', 'mostly_out', 'mountain_out']


def daylight(payload, now):
    """Use real sunrise/sunset intervals; unbracketed or malformed data is unknown."""
    unavailable = dict(state='unknown', explanation='Daylight data is unavailable or does not cover this time.')
    try:
        daily = payload['daily']
        rises, sets = daily['sunrise'], daily['sunset']
        if not isinstance(rises, list) or not isinstance(sets, list) or not rises or len(rises) != len(sets):
            return unavailable
        intervals = []
        for rise, setting in zip(rises, sets):
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (rise, setting)):
                return unavailable
            if not 0 < setting - rise < 86400:
                return unavailable
            # Also validate timestamps before including them in public diagnostics.
            datetime.fromtimestamp(rise, UTC)
            datetime.fromtimestamp(setting, UTC)
            intervals.append((rise, setting))
        intervals.sort()
        if any(intervals[i][1] >= intervals[i + 1][0] for i in range(len(intervals) - 1)):
            return unavailable
        timestamp = now.timestamp()
        for rise, setting in intervals:
            if rise <= timestamp < setting:
                return dict(state='daylight', sunrise_at=datetime.fromtimestamp(rise, UTC).isoformat(),
                            sunset_at=datetime.fromtimestamp(setting, UTC).isoformat())
        earlier = [setting for _, setting in intervals if setting <= timestamp]
        later = [rise for rise, _ in intervals if rise > timestamp]
        if earlier and later and 0 < min(later) - max(earlier) < 86400:
            return dict(state='night', previous_sunset_at=datetime.fromtimestamp(max(earlier), UTC).isoformat(),
                        next_sunrise_at=datetime.fromtimestamp(min(later), UTC).isoformat())
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        pass
    return unavailable


def _gate(weather, observability, now):
    try:
        if observability['state'] == 'daylight':
            covered = datetime.fromisoformat(observability['sunrise_at']) <= now < datetime.fromisoformat(observability['sunset_at'])
        elif observability['state'] == 'night':
            covered = datetime.fromisoformat(observability['previous_sunset_at']) <= now < datetime.fromisoformat(observability['next_sunrise_at'])
        else:
            covered = True
    except (KeyError, TypeError, ValueError):
        covered = False
    if not covered:
        observability = dict(state='unknown', explanation='Daylight data no longer covers this evaluation time.')
    result = dict(weather)
    result['weather_conditions'] = {key: weather[key] for key in
                                    ('status', 'verdict', 'explanation', 'limiting_factors') if key in weather}
    result['observability'] = observability
    if weather['status'] != 'unknown' and observability['state'] != 'daylight':
        night = observability['state'] == 'night'
        result.update(status='unknown', verdict='UNKNOWN',
                      explanation='Outside daylight hours; weather alone cannot confirm the view.' if night
                                  else 'Daylight information is unavailable; visual assessment is uncertain.',
                      limiting_factors=['darkness' if night else 'daylight_data_unavailable'])
    return result


def calculate_v2(payload, now, fetched_at, location, baseline=None):
    baseline = calculate(payload, now, fetched_at, location) if baseline is None else baseline
    result = dict(baseline)
    result['model'] = 'local-weather-v2-candidate'
    inputs = baseline.get('weather_inputs')
    if inputs is not None:
        inputs = dict(inputs)
        layers_available = inputs.get('cloud_cover_low') is not None and inputs.get('cloud_cover_mid') is not None
        cloud = max(inputs['cloud_cover_low'], inputs['cloud_cover_mid']) if layers_available else inputs['cloud_cover']
        inputs['effective_cloud_cover'] = cloud
        result['weather_inputs'] = inputs
        result['cloud_basis'] = 'low_mid_layers' if layers_available else 'total_cloud_fallback'
        limits = dict(
            cloud_cover=4 if cloud <= 15 else 3 if cloud <= 35 else 2 if cloud <= 60 else 1 if cloud <= 85 else 0,
            visibility=0 if inputs['visibility'] < 5000 else 1 if inputs['visibility'] < 10000 else 2 if inputs['visibility'] < 20000 else 4,
            precipitation=0 if inputs['precipitation'] >= 1 else 1 if inputs['precipitation'] > 0 else 4,
            weather_code=0 if inputs['weather_code'] in {45, 48, 65, 67, 75, 82, 86, 95, 96, 99}
                         else 1 if inputs['weather_code'] >= 51 else 4,
        )
        level = min(limits.values())
        result.update(status=STATES[level], verdict=LABELS[level].upper(),
                      explanation='Layer-aware weather candidate; cloud heights and the actual sight line are unverified.',
                      limiting_factors=[key for key, cap in limits.items() if cap == level and level < 4])
    return _gate(result, daylight(payload, now), now)


def corridor_v2(results, points, now, location, observability=None):
    # Reuse v1's freshness validation and haze diagnostic, but score the weather
    # conditions before daylight gating and remove its extra distance cap.
    weather = [{**result, **result['weather_conditions']} for result in results]
    result = calculate_corridor(weather, points, now, location)
    result.pop('weather_conditions', None)
    result.pop('observability', None)
    result.pop('cloud_basis', None)
    result['model'] = location['id'] + '-corridor-v2-candidate'
    if result['status'] != 'unknown':
        level = min(STATES.index(sample['status']) for sample in weather)
        result.update(status=STATES[level], verdict=LABELS[level].upper(),
                      explanation='Layer-aware corridor candidate without a distance/visibility cap; not a confirmed view.',
                      limiting_factors=['corridor_weather'] if level < 4 else [])
    return _gate(result, observability if observability is not None else
                 results[0]['observability'] if results else dict(state='unknown'), now)


def compare_models(v1, v2, active_model='v1'):
    """Select the displayed estimate while retaining both models' full evidence."""
    if active_model not in ('v1', 'v2'):
        raise ValueError('WEATHER_MODEL must be v1 or v2.')
    return {**(v2 if active_model == 'v2' else v1),
            'model_comparison': dict(active_model=active_model, v1=v1, v2=v2,
                                     agrees=v1['status'] == v2['status'])}
