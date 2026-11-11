# Model v2.1: provisional default and submission-time evidence

V2.1 is the experimental, uncalibrated default weather estimate. A maintainer's
webcam report and the corresponding Seattle API inputs exposed a false NOT OUT
prediction in both v1 and the initial v2.0. V2.1 removes mid-cloud coverage as a
hard obstruction and the 10–20 km surface-visibility cap. These are qualitative
rule changes prompted by an observed failure, not evidence of validated accuracy.
V1 remains available in every response and as a rollback setting. Community-report
overrides retain their existing 20-minute policy.

The Worker reads `WEATHER_MODEL`, configured as `v2` in `wrangler.jsonc`. The `v2`
selection now runs revision 2.1, identified by `v2.1-candidate` in model IDs so
evaluation does not silently pool its results with the initial v2. Set the variable
to `v1` and redeploy to roll back without changing the algorithms, weather cache
or stored reports. An authenticated maintainer can also use
`npx wrangler deploy --var WEATHER_MODEL:v1`; the next ordinary deployment uses
the repository's configured value again. The Python server defaults to v2 and
accepts `--weather-model v1`; the `WeatherService` library retains its v1 default
for existing callers and accepts `active_model='v2'` explicitly.

The Python implementation is `mountain/model_v2.py`; the Worker implementation
is `cloudflare/src/model-v2.js`. Cross-language tests compare full normalized
outputs for cloud layers, local weather limits, daylight boundaries, missing data
and all three geographic corridors.

## Candidate rules

- When both low and mid cloud layers are available, use low-cloud coverage as
  the obstruction proxy, with the existing qualitative cloud thresholds. Mid
  coverage above the existing 15% clear-condition boundary caps the result at
  MOSTLY OUT. It is uncertainty about an unmeasured cloud height, not proof that
  the summit is hidden. Retain total/high cloud as diagnostics. If either lower
  layer is missing, fall back to total cover as before.
- Below 5 km surface visibility, retain NOT OUT; from 5 to below 10 km, retain
  the KINDA OUT cap. At 10 km and above, do not apply a visibility-only cap.
  Surface meteorological visibility is not a hard summit viewing-distance limit.
  Retain precipitation, fog and severe-weather caps unchanged.
- Retain the worst weather sample across the corridor. Compute and retain the
  same `haze_index` for comparison, but do not apply its extra distance/visibility
  cap to v2.
- Apply the observer's daylight gate to the aggregate. Weather conditions at
  remote samples do not become missing just because their daylight information
  is absent. Missing or stale weather at any required sample still yields UNKNOWN.

Cloud-layer percentages do not provide cloud-base heights or a measured sight
line. V2 does not invent those heights, infer exact visible fractions or claim
that high clouds can never matter. Terrain, elevated rays, illumination, moonlight
and webcams remain outside this candidate's scope. The revised cloud rule needs the
same observation-based evaluation as the removed distance cap.

## Diagnosed Seattle false negative

At `2026-11-11T22:35:45.743Z`, the live response confirmed v2 was active, weather
was the display basis, and no community votes were present. Across the four
samples, low cloud was 0%, mid cloud was 100/100/100/42%, high cloud was 100%,
visibility was 18,800/20,200/30,500/33,500 m, precipitation was zero, and WMO code
was 3 (overcast, not fog). Daylight was valid. All forecasts selected 23:00 UTC.
The original `max(low, mid)` rule forced NOT OUT in the first three samples;
the fourth was HALFWAY OUT. The worst-sample aggregation therefore returned NOT OUT.
Switching back to v1 would retain the failure.

The [recorded input fixture](../tests/fixtures/seattle-2026-11-11-mid-cloud.json)
retains the selected inputs and solar interval, not an invented provider response.
Replaying it gives NOT OUT under the original v2.0 and MOSTLY OUT under v2.1,
with `mid_cloud_cover` as each sample's limiting factor. The uncertainty cap avoids
claiming a confirmed clear view. A maintainer reported the mountain visible on
webcams; exact camera identity and frame time were not supplied. This case is a
regression example used to develop the change, not held-out validation. Other
viewpoints were reported wrong too, but their live inputs were not provided.

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

The Worker now prefixes cache keys with `solar-v1:` so pre-rollout responses
without daily data are refreshed on the first request. Both models share those
new entries with the usual 15-minute policy. Old entries expire through normal
cleanup. Reports, QR contexts and the database schema are preserved.

The 5 km and 10 km poor-visibility thresholds and low-cloud proxy remain
uncalibrated. Removing the 20 km cap does not establish that haze, low cloud or
mid cloud cannot hide a summit. Review further cases against timestamped webcams.

## API fields

The top-level weather fields describe the selected model. Both complete model
results, including timestamps, inputs and location metadata, are retained:

```json
{
  "model_comparison": {
    "active_model": "v2",
    "v1": {
      "model": "seattle-corridor-v1-uncalibrated",
      "status": "kinda_out"
    },
    "v2": {
      "model": "seattle-corridor-v2.1-candidate",
      "status": "mountain_out",
      "observability": {"state": "daylight"},
      "weather_conditions": {"status": "mountain_out"}
    },
    "agrees": false
  }
}
```

This abbreviated example is a fixture, not live weather. Both versions retain
their full weather evidence; neither model contains another comparison object.
`agrees` compares status strings, not accuracy. The active-model field refers to
the weather model; `display_basis` still identifies a community override.

Candidate cloud diagnostics use `weather_inputs.effective_cloud_cover` for the
candidate's own input rule. Local candidates expose `cloud_basis` as
`low_layer_with_mid_uncertainty` or `total_cloud_fallback`. Corridor inputs remain attached to
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
and avoid pooling repeatedly correlated reports as independent truth. The
provisional v2 default is an operational choice, not a claim of validation.

## Current checks

The implementation is covered by 66 Python tests and 14 Worker/Node tests,
including the Worker build dry run, full Python/JavaScript candidate parity,
provider-query/caching checks, the recorded Seattle regression, default selection
and rollback, solar boundaries, stale and missing samples,
submission snapshots, replay immutability and evaluation-tool accounting.
The mobile feedback flow is also exercised with Chromium and fixture weather.
These checks establish implementation behavior, not measured improvement in
mountain-visibility accuracy. Live provider access and deployment are separate.
