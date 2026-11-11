# Model v2: shadow comparison and submission-time evidence

V2 is an experimental, uncalibrated candidate. The API continues to use v1 for
the displayed weather estimate. Community-report overrides retain their existing
20-minute policy. No automatic promotion or threshold fitting is implemented.

The Python implementation is `mountain/model_v2.py`; the Worker implementation
is `cloudflare/src/model-v2.js`. Cross-language tests compare full normalized
outputs for cloud layers, local weather limits, daylight boundaries, missing data
and all three geographic corridors.

## Candidate rules

- When both low and mid cloud layers are available, use their maximum as the
  cloud-obstruction proxy. Retain total/high cloud as evidence but do not let
  high cloud alone impose a NOT OUT cap. If either lower layer is missing, fall
  back to total cover. Existing cloud thresholds remain qualitative hypotheses.
- Retain v1's local visibility, precipitation, fog and severe-weather caps. High
  cloud may be context, but actual local fog or rain still reduces the estimate.
- Retain the worst weather sample across the corridor. Compute and retain the
  same `haze_index` for comparison, but do not apply its extra distance/visibility
  cap to v2.
- Apply the observer's daylight gate to the aggregate. Weather conditions at
  remote samples do not become missing just because their daylight information
  is absent. Missing or stale weather at any required sample still yields UNKNOWN.

Cloud-layer percentages do not provide cloud-base heights or a measured sight
line. V2 does not invent those heights, infer exact visible fractions or claim
that high clouds can never matter. Terrain, elevated rays, illumination, moonlight
and webcams remain outside this candidate's scope. The low/mid rule needs the
same observation-based evaluation as the removed distance cap.

## Daylight handling

The shared Open-Meteo request adds `daily=sunrise,sunset` and `past_days=1` to
the existing UTC Unix-time request with two forecast days. Both versions consume
the same response; evaluating the candidate adds no provider requests. Requesting
the preceding day makes the previous sunset available around UTC midnight.

The UTC boundary handling was checked against Open-Meteo's
[official solar-event implementation](https://github.com/open-meteo/open-meteo/blob/a358d6c591f21f3adbdcfa10517f761d688b527d/Sources/App/Helper/Solar/SunRiseSet.swift).
It returns absolute event timestamps and permits sunset to extend beyond the
UTC date boundary; the candidate compares those timestamps directly.

Solar intervals are validated as finite Unix timestamps with matching array lengths,
positive durations below 24 hours and no overlapping intervals. Daylight includes
sunrise and excludes sunset. Night is established only between a known previous
sunset and next sunrise separated by less than 24 hours. Missing, malformed,
unbracketed or out-of-coverage data yields unknown observability.

At night v2 returns `status: unknown`, with `limiting_factors: ["darkness"]`.
With unavailable daylight data, its reason is `daylight_data_unavailable`. In
both cases `weather_conditions` retains the weather-only status, verdict and
limits. Darkness is not represented as NOT OUT. Unknown weather remains unknown
for its weather reason rather than acquiring an invented weather assessment.
The observer's daylight is evaluated again at corridor evaluation time, so a
sunset occurring while the route's samples load cannot leave a daylight verdict.

This is a conservative solar-day check, not a camera observation or a claim that
the mountain cannot be seen before sunrise or under moonlight.

Existing cache rows without daily data keep v1 working normally and make v2
UNKNOWN until refreshed by the normal 15-minute cache policy. There is no cache
or schema migration.

## API fields

The original top-level weather fields and v1 model identifier remain. Added:

```json
{
  "model_comparison": {
    "active_model": "v1",
    "v1": {
      "model": "seattle-corridor-v1-uncalibrated",
      "status": "kinda_out"
    },
    "v2": {
      "model": "seattle-corridor-v2-candidate",
      "status": "mountain_out",
      "observability": {"state": "daylight"},
      "weather_conditions": {"status": "mountain_out"}
    },
    "agrees": false
  }
}
```

This abbreviated example is a fixture, not live weather. V1 is a summary; v2 is
the full candidate with timestamps, weather evidence and location metadata.
`agrees` compares status strings, not accuracy. The active-model field refers to
the weather model; `display_basis` still identifies a community override.

Candidate cloud diagnostics use `weather_inputs.effective_cloud_cover` for the
candidate's own input rule. Local candidates expose `cloud_basis` as
`low_mid_layers` or `total_cloud_fallback`. Corridor inputs remain attached to
individual samples. V1 evidence is kept separately and is not mutated by v2.

## Reports: original versus submission-time forecasts

After a valid form is submitted, evaluate the weather models at submission time
using the normal shared cache. Do not use current community votes as weather
evidence. Save the original QR-linked weather estimate in the existing `snapshot`
JSON, and add its `submission_weather_estimate` child containing the current
v1/v2 comparison. The original QR context remains unchanged.

The receipt's agreement/disagreement uses the submission-time active weather
estimate. Unknown current weather does not prevent saving the observation and
does not receive an agreement score. The reported conditions still expire under
the existing policy. No new database column, public report-export endpoint or
longer retention is introduced.

In the Worker, identical retries retain their original timestamp and entire
snapshot; a changed answer is a new explicit observation and gets a newly
evaluated forecast. In the Python development collector, existing ten-minute
duplicate suppression remains, and duplicates do not re-evaluate weather. Its
private review queue flags disagreement with either submission-time model.
Older records fall back to their original display comparison for inspection,
but the quantitative evaluation tool excludes them.

## Evaluate collected observations

These are private operator commands, not public routes. Reports are unverified
observations: account login, if added later, will still not make them ground truth.

For the Python collector:

```sh
mkdir -p .local/evaluation
.venv/bin/python -m mountain.feedback export --data-dir /YOUR/PRIVATE/DIRECTORY > .local/evaluation/reports.jsonl
.venv/bin/python tools/evaluate_models.py .local/evaluation/reports.jsonl --since 2026-11-11
```

For the shared Worker, run from an authenticated maintainer environment:

```sh
mkdir -p .local/evaluation
npx wrangler d1 execute mountain-feedback --remote --command 'SELECT received,mountain,viewpoint,answer,snapshot FROM reports ORDER BY received' --json > .local/evaluation/reports.json
.venv/bin/python tools/evaluate_models.py .local/evaluation/reports.json --since 2026-11-11
```

The tool accepts JSON Lines, an array of rows, or Wrangler's JSON `results`
wrapper. String-valued D1 snapshot JSON is decoded. `--since` is inclusive;
`--until` is exclusive. ISO offsets are supported; dates/times without an offset
use UTC. Keep exports private and apply the same 90-day retention to backups.

Output separates each mountain/viewpoint and pair of model identifiers. It shows
same/different/uncompared counts per model, plus paired comparisons only when both
models make a comparable prediction. UNKNOWN/abstention counts remain visible;
an increase in UNKNOWN must not look like an accuracy improvement. Can't-tell
answers and records without a submission-time comparison are counted as skipped.
Empty or all-skipped input is not validation of either model.

Use earlier observations for hypothesis development and a later, held-out date
range for comparison. Review actual disagreement cases, age differences, daylight
coverage and input completeness at each viewpoint. Keep conflicting observations
and avoid pooling repeatedly correlated reports as independent truth. Promotion
to the displayed model is a separate explicit change after evaluation.

## Current checks

The implementation is covered by 64 Python tests and 11 Worker/Node tests,
including the Worker build dry run, full Python/JavaScript candidate parity,
provider-query/caching checks, solar boundaries, stale and missing samples,
submission snapshots, replay immutability and evaluation-tool accounting.
The mobile feedback flow is also exercised with Chromium and fixture weather.
These checks establish implementation behavior, not measured improvement in
mountain-visibility accuracy. Live provider access and deployment are separate.
