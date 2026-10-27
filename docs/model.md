# Weather model and normalized result

These thresholds are qualitative heuristics, **not calibrated probabilities**.
Forecasts near the observer cannot establish what is happening along the entire
viewing path or on the summit. No community website status is used.

## Calculation

Open-Meteo `/v1/forecast` receives observer latitude/longitude, `timezone=UTC`,
`timeformat=unixtime`, `forecast_days=2` and hourly cloud cover (total, low, mid,
high), visibility (metres), precipitation (mm), and WMO weather code.
UTC epoch timestamps avoid DST ambiguity. The closest forecast hour is selected;
ties choose the first hour in the response. A forecast hour more than 90 minutes
away in either direction, a response older than 60 minutes, or a future retrieval
timestamp returns UNKNOWN. The regular response cache lasts only 15 minutes.

Total cloud cover, visibility, precipitation and weather code must all be finite
and valid. Missing/null layer values are optional; available layers must be valid.
The largest available layer or total cover determines the initial status:

| Effective cloud cover | Initial verdict |
| --- | --- |
| 0–15% | Mountain OUT! |
| >15–35% | Mostly Out |
| >35–60% | Halfway Out |
| >60–85% | Kinda Out |
| >85–100% | Not Out |

Visibility caps the result: below 5 km → Not Out, 5–<10 km → at most Kinda Out,
10–<20 km → at most Halfway Out, ≥20 km → no additional cap.
Precipitation ≥1 mm/hour, fog (45/48), or severe weather (65/67/75/82/86/95/96/99)
forces Not Out. Any lighter precipitation or remaining precipitation weather code
(51+) caps it at Kinda Out. These conservative choices can be wrong, especially
when a mountain rises above low cloud. Numerical weather codes are validated
against the WMO codes supported by Open-Meteo.

## Data contract

`GET /api/visibility?viewpoint=paradise`
returns a small JSON object. Example fields (illustrative, not live):

```json
{
  "status": "mostly_out",
  "verdict": "MOSTLY OUT",
  "explanation": "Conditions favour a view, with some cloud possible.",
  "location": {"name": "Paradise", "latitude": 46.786, "longitude": -121.735},
  "forecast_at": "2026-10-27T19:00:00+00:00",
  "fetched_at": "2026-10-27T19:10:00+00:00",
  "checked_at": "2026-10-27T19:14:00+00:00",
  "forecast_at_label": "Oct 27 12:00 PDT",
  "fetched_at_label": "Oct 27 12:10 PDT",
  "checked_at_label": "Oct 27 12:14 PDT",
  "source": "Open-Meteo",
  "estimate": true
}
```

Statuses: `not_out`, `kinda_out`, `halfway_out`, `mostly_out`, `mountain_out`,
`unknown`. `forecast_at` is the valid time of the forecast hour, **not** an
observation or model issue time. `fetched_at` is when this service retrieved the
response; `checked_at` is when it evaluated this request, including cache hits.
The provider does not supply an issue timestamp here. Display labels use
America/Los_Angeles with explicit PST/PDT; machine timestamps are UTC.
Provider failures have null forecast/fetched timestamps and Unavailable labels.
Stale/invalid payloads produce UNKNOWN with a reason. API HTTP errors, network
timeouts and malformed JSON do not become Not Out.

Any new provider should normalize its own data before calling the model or
replace the provider/model adapter while retaining this rendering contract.

## Seattle corridor

Seattle is the default (`?viewpoint=seattle`), at Kerry Park (47.6295, -122.3599).
Paradise is `?viewpoint=paradise`. Arbitrary coordinate overrides are no longer
supported by the public API; this keeps illustrations matched to observer presets.
Seattle’s four sample coordinates interpolate at 0, 1/3, 2/3 and 1 of the route to
Rainier’s approximate summit (46.8523, -121.7603). This is a geographic corridor,
not a terrain profile. Near-summit surface forecasts do not resolve all summit clouds.

Each sample uses the same validated local cloud/rain/fog logic above. All four
must be complete and fresh, including when evaluated at the final response time;
otherwise the result is UNKNOWN. The poorest sample sets an initial ceiling.
The additional haze index sums each segment’s distance in metres multiplied by
the mean reciprocal visibility at its two endpoints (visibility floored at 1 m
only to prevent division by zero). This dimensionless, uncalibrated heuristic
increases with route distance and haze. It is not a probability or a physically
validated atmospheric transmittance calculation.

| Haze index | Maximum verdict |
| --- | --- |
| ≤1 | Mountain Out |
| >1–2 | Mostly Out |
| >2–4 | Halfway Out |
| >4–8 | Kinda Out |
| >8 | Not Out |

For example, uniform 30 km visibility over this roughly 98 km route caps the
estimate at Halfway Out, while the local Paradise model can still return Mountain
Out. Provider visibility ceilings and surface/elevated-path differences can make
this conservative cap wrong; observation-based calibration remains required.

Seattle results expose `model`, `distance_m`, `haze_index`, and `corridor_samples`
with per-point coordinates, verdicts, forecast/retrieval times and visibility.
The aggregate uses the oldest contributing forecast and retrieval timestamps;
`checked_at` is the aggregate evaluation time. All responses include `viewpoint`
and `image_path` so Liquid selects the corresponding generated artwork even on
UNKNOWN results. Paradise uses `local-weather-v1-uncalibrated`, Seattle uses
`seattle-corridor-v1-uncalibrated`. Each coordinate is cached independently for
15 minutes, with a 60-second transport-error backoff.

## Multiple mountains and location presets

`mountain=rainier` is the default, with `viewpoint=seattle` (default), `tacoma`, or
`paradise`. `mountain=hood` accepts `viewpoint=portland` (default for Hood).
Unsupported pairs are rejected, never silently reinterpreted. Each observer record
carries the mountain ID, name, coordinates and image path. `MOUNTAINS` supplies the
correct target summit; all corridor samples interpolate toward that target.
Tacoma and Portland use the same distance-sensitive haze penalty documented above,
not Seattle’s distance or Rainier’s summit. Paradise retains its single-point model.
Results include `mountain` as well as `viewpoint`, and per-route evidence remains
available for each corridor. Missing route samples still produce UNKNOWN.

State illustration lives in Liquid/SVG, separately from these calculations.
Opaque clouds obscure increasing fractions of the selected viewpoint artwork;
UNKNOWN uses an unfilled dashed outline instead of suggesting atmospheric conditions.
Cloud locations and shape do not encode measured cloud altitude, position or opacity.
