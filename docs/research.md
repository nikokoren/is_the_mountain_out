# Optional next phases

These are research leads, not implemented or verified integrations. No webcam
images, terrain tiles, or historical observations were downloaded for this release.

## Terrain and line of sight

Start with [USGS 3DEP](https://www.usgs.gov/3d-elevation-program) for US elevation
coverage or [SRTM](https://www.earthdata.nasa.gov/data/instruments/srtm) for a global
baseline. Verify dataset resolution, vertical datum, access terms and attribution.
Rainier's approximate summit is 46.8523 N, 121.7603 W, 4,392 m; verify the selected
summit and datum before treating these values as survey data.

Compute observer-to-summit distance/bearing and sample a terrain profile along
that ray. Include observer height and curvature/refraction assumptions for longer
paths. Cache elevation tiles and derived profiles per observer, not per refresh.
Test against known obstructed/unobstructed viewpoints. A clear terrain line of
sight says nothing about atmospheric opacity. Hourly cloud percentages do not
reliably provide cloud-base heights; do not invent a cloud-height estimate.

## Webcam verification

The [NPS Mount Rainier webcam directory](https://www.nps.gov/mora/learn/photosmultimedia/webcams.htm)
is the starting point, particularly the Paradise mountain camera. Before building:

1. Confirm the maintained camera endpoint, image timestamp, update frequency,
   availability, and whether direct image requests are supported.
2. Verify reuse permissions and attribution for that exact image/feed, including
   third-party credits. A federal landing page alone does not settle every image's rights.
3. Detect frozen images, darkness, snow on the lens and camera outages independently
   of mountain visibility. Track camera acquisition time separately from weather.
4. Collect a permitted, seasonally diverse labelled sample and compare with the
   unchanged Phase 1 model. Measure errors on held-out dates before tuning thresholds.
5. Add image analysis only when it improves accuracy, with explicit weather-only
   fallback and separate provenance for verified versus estimated verdicts.

Do not scrape isthemountainout.com or use its internal status. It is not a promised
public API and its terms restrict commercial scraping/bulk extraction.

## Calibration plan

Record forecast hour, retrieval time, observer, input metrics, verdict, and an
independent permitted observation time. Compare low-cloud, summit-cloud, fog,
precipitation and clear-observer/cloudy-summit cases across seasons. Avoid using
the same images for tuning and evaluation. Keep uncertainty visible and reserve
numerical probabilities for a genuinely calibrated model.
