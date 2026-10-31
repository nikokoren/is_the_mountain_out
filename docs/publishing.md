# Recipe publication preparation

Status: reviewed against the TRMNL team's checklist; local materials prepared.
Public submission still needs the layout decision, hosted and account-level checks below.

Source: Mario Lurig, [A Checklist for Turning a Private Plugin into a Recipe for
Others](https://trmnl.com/blog/plugin-recipe-publishing-tips), April 27, 2026,
read from the user-provided PDF on October 31, 2026. The article describes
automated CHEF feedback followed by human review; local validation does not
replace either step. Its optional polish suggestions are identified separately
from publishing requirements below.

## Review against the article

| Area | Finding and preparation | Remaining check |
| --- | --- | --- |
| Ecosystem | Rainier and Hood, four viewpoints and all layouts remain in one recipe. Its identifiable focus is viewpoint-specific mountain illustrations, a conservative weather estimate and optional short-lived local reports. Defaults are family friendly. | Search the current catalog for similar recipes and explain the distinct value in the submission. Catalog access is unavailable here. |
| Author and categories | Added the `life` category, an explicit author contact/issues link and a README link to `author_bio`. The form explains that the shared service connects automatically and that users need no deployment, Cloudflare account or API key. Descriptions use HTML links and deliberate `<br/>` breaks. | Confirm the category and links in the hosted installation form, and that repository issues are enabled and monitored. |
| Defaults and fields | There is no service URL field, visible or hidden. Users choose mountain/viewpoint and optional feedback. Dropdown defaults use option values; dependent dropdowns are optional until selected by conditional validation. No `optional: false` is present. QR remains off by default. | Change, save and inspect every field in TRMNL, including switching mountains with previously saved hidden values. Remove the obsolete service field from existing installations. |
| Polling | Uses one GET URL pointing directly to the author's shared Worker. Weather calls happen on the backend, not during rendering. No randomized endpoint is used. Local Liquid tests cover active viewpoint selection, missing-field defaults and checkbox encodings; Worker tests cover enabled and disabled feedback values. | Use TRMNL's polling Parse feature against the shared service and verify actual saved form values. |
| Markup | Uses native Framework 3.4.0 classes, shared Liquid and explicit render arguments. The shared template defines the artwork origin directly, so neither rendering nor polling depends on saved `service_url` values or native `trmnl` variables. No custom CSS, opacity, fonts, client API calls, charting or custom JavaScript is present in the recipe. | Confirm with CHEF and hosted rendering. The backend's normal HTML feedback page is separate from recipe markup. |
| Layouts | Local checks cover all four views on OG and X, including X portrait, clipping, legibility, QR presence and scan decoding. Native text fitting handles verdict length. Visual review found substantial whitespace in tall views, especially X portrait half-vertical, despite passing bounds checks. | Decide whether to retain the minimal composition or add useful content in tall views before submission, then inspect the hosted renderer and device output. |
| Privacy and examples | Export deliberately contains the public shared Worker origin confirmed by the author; that address is public configuration, not a credential. Test QR payloads use `mountain.example.com` and are never requested. Fixture QR links are explicitly examples. | Review final submission screenshots and any demo data captured from the deployed service. |
| Optional polish | Shared markup already avoids duplication. No title bar or default TRMNL logo needs replacement. External artwork remains hosted with the service; inline images are a nice-to-have in the article, not a requirement. | Consider inline static artwork later if external asset availability proves unreliable. |

## Suggested listing copy

**Name:** Is the Mountain Out?

**Short description:** Rainier or Hood on your TRMNL, with viewpoint-specific
illustrations, weather estimates and optional community reports.

**Description:** Is Mount Rainier / Tahoma out from Seattle, Tacoma or Paradise?
How about Mount Hood / Wy’east from Portland? Choose a viewpoint and see a simple
illustrated verdict, from MOUNTAIN OUT! to NOT OUT, with UNKNOWN when conditions
cannot be determined. All four layouts are included. An optional QR code on Full
lets people near the viewpoint report what they see.

**Installation:** Install the recipe, choose a mountain/viewpoint, and optionally
enable the Full-layout feedback QR. Data and artwork come from the author's
shared service automatically. No backend deployment, Cloudflare account, API key
or service URL entry is needed. Refresh is every 15 minutes.

**Shared service:** The public origin is
`https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev`.
Weather caching and community reports are shared across installations; a report
can affect other displays at the same mountain/viewpoint. The maintainer operates
the Worker and D1 database and handles provider terms, usage and service availability.

**Accuracy and reports:** Weather estimates are uncalibrated and do not verify
the actual view. Artwork is generated illustration, not a live camera image.
Optional community reports are unverified and count for 20 minutes; conflicting
reports show UNKNOWN. With no informative current reports, weather estimates
resume. Displayed information may remain on the device after its source expires
or if refresh fails. This recipe does not provide live visual confirmation.

**Source, setup and support:** https://github.com/nikokoren/is_the_mountain_out
Use repository issues for problems, with mountain/viewpoint, layout, device,
refresh time and redacted error output. Do not post cookies or feedback tokens.

## Submission materials

- Build the import archive from the repository root:
  `.venv/bin/python tools/package_plugin.py`. The default export is
  `releases/is-the-mountain-out.zip`; it contains settings and
  all five Liquid files. Polling and artwork already use the shared public origin;
  the export has no service URL installation field. The `--service-url` packaging
  option is solely for maintainers exporting local development or separate forks.
- Use `docs/clear-fixture.png` as a candidate full-layout screenshot and
  `docs/previews/*-states.png` to review the six display states at each viewpoint.
  [Layout review sheet](publishing-layouts.png) shows all four layouts on OG
  landscape, X landscape and X portrait, captured locally with official Framework
  assets. Identify fixtures as examples, not live conditions. The article does
  not specify upload dimensions or icon requirements; confirm those in the
  submission UI. Existing logo assets are candidates, not verified submission assets.
- Keep the feedback QR off by default. A QR in a fixture is not a working report
  link. Produce any final QR screenshot from your deployed service.

Regenerate the layout sheet with `.venv/bin/python tools/review_layouts.py`.
Individual full-resolution captures are saved under `.local/publishing/screens/`.
The sheet deliberately shows the sparse tall layouts; it is a review aid, not
evidence that the article's whitespace criterion has passed.

## Release checks

- [x] Read the TRMNL team publishing-preparation article and complete the local
  review above; update form guidance, metadata and sanitized examples.
- [ ] Compare with the current recipe catalog and document the distinct value.
- [ ] Resolve the tall-layout whitespace finding, balancing the existing minimal
  design with the article's request to fill the screen with useful content.
- [ ] Verify the existing shared Worker: health, all four weather
  endpoints and image assets. An UNKNOWN fallback alone does not prove that
  live weather access works. Review provider terms and operational limits.
  Deploy the updated landing page through the maintainer's deployment flow.
- [ ] Import the ZIP into TRMNL and verify automatic shared-service connection, defaults,
  conditional viewpoint fields, polling interpolation and feedback opt-in.
- [ ] Preview all four layouts with the hosted renderer, including UNKNOWN,
  all viewpoint artwork, and QR on/off. Local browser checks are separate.
- [ ] Check a physical TRMNL display for legibility and refresh behavior. Scan a
  live Full-layout QR, submit an observation and verify receipt and later refresh.
- [ ] Verify privacy/retention information and support destination are suitable
  for the public service. Review deployment-specific logging and abuse controls.
- [ ] Run CHEF on the installed plugin, resolve its findings, then submit for
  TRMNL's human review with final assets after the above checks.

Additional repository recommendation, separate from the article's checklist:
choose appropriate licensing/reuse terms and confirm rights to code and
generated/reference artwork. No LICENSE is present. The owner's license choice
has not been inferred or added during this review.

## Local validation

Validated on 2026-10-31: deployment dry run and seven Worker/D1 tests passed;
all 44 Python tests passed, including active-mountain polling selection,
default fields, feedback encodings, legacy-field independence and consistent
polling/artwork origins in the default and maintainer-override exports;
the browser feedback flow saved an observation and verified its receipt/review;
the six-file import ZIP was generated and passed its archive integrity check.
All 408 responsive layout cases passed across five device profiles, both
orientations and all four layouts, including 51 successfully decoded QR screenshots.
Local Worker health, landing page and artwork requests returned HTTP 200.
A local live-weather request returned UNKNOWN with an unavailable/stale corridor
forecast, so live provider access remains unverified.
The author confirmed the shared production origin, but a direct health request
from this environment was denied by its network proxy with HTTP 403. This does
not establish a Worker outage. Its hostname was added to the saved environment
network draft; runtime verification needs those settings applied.

Use the existing commands from the repository root:

```sh
npm ci
npm test
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/check_layouts.py
.venv/bin/python tools/review_layouts.py
.venv/bin/python tools/check_feedback.py
.venv/bin/python tools/package_plugin.py
```

See the README for Python dependencies and the official Framework asset cache
required by the browser checks. Local tests do not validate TRMNL account
settings, public deployment, weather-provider authorization or physical output.
