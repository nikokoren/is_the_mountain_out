# Visibility model and submission authentication review

Reviewed November 11, 2026, on the existing shared-Worker review branch. This is
a code and controlled-fixture review, not an evaluation against live observations
or evidence of a deployed change. The production weather model is implemented in
`cloudflare/src/model.js`; `mountain/model.py` is the Python reference, with parity
tests. The anonymous report overrides are implemented by the Worker, not by the
Python development collector.

## How the verdict is inferred

1. Select a fixed mountain/viewpoint. Seattle, Tacoma and Portland use four
   evenly spaced geographic samples toward the relevant summit; Paradise uses
   one local sample.
2. Fetch Open-Meteo hourly total/layer cloud cover, visibility, precipitation and
   WMO weather code. Select the nearest forecast hour, within 90 minutes, from a
   response fetched no more than an hour ago. Normal caching lasts 15 minutes.
3. Convert the largest cloud-cover value to one of five qualitative statuses.
   Cap that status for low visibility, precipitation, fog and severe weather.
4. For a corridor, choose the worst sample status and then apply an additional
   cap from segment distance divided by surface visibility.
5. In the shared Worker, current community reports can replace this estimate for
   20 minutes per report. Any informative unopposed answer is sufficient; conflicting
   current answers produce UNKNOWN. With no informative reports, weather resumes.

None of these steps measures the visible fraction of a mountain. The labels and
cloud illustration are qualitative, not calibrated fractions or probabilities.

## Findings and recommended order of improvements

### 1. Audit the distance/visibility penalty before tuning thresholds

Controlled fixtures with no cloud/rain and weather code 0 at every sample:

| Viewpoint | Corridor length | Uniform 24 km visibility | Uniform 30 km visibility | Uniform 120 km visibility |
| --- | --- | --- | --- | --- |
| Seattle | 97.6 km | KINDA OUT | HALFWAY OUT | MOUNTAIN OUT! |
| Tacoma | 71.3 km | HALFWAY OUT | HALFWAY OUT | MOUNTAIN OUT! |
| Portland | 81.4 km | HALFWAY OUT | HALFWAY OUT | MOUNTAIN OUT! |
| Paradise | Local sample | MOUNTAIN OUT! | MOUNTAIN OUT! | MOUNTAIN OUT! |

The distance penalty alone causes these differences. Surface meteorological
visibility is not a hard maximum distance at which an elevated summit is visible.
Provider/model ceilings can also make a high reported value ambiguous. A 24 km
reading in this example is not evidence that a particular provider has a 24 km
ceiling; that needs verification for the model actually used.

Measure false negatives against time-matched observations, identify any provider
ceiling, then evaluate a versioned candidate model. Do not silently remove the
penalty or pick a more optimistic cutoff without those observations.

### 2. Separate cloud cover from clouds obscuring the sight line

A fixture with 10% total cover, 95% high-cloud cover, no rain and 120 km visibility
produces NOT OUT. Even 100% overhead cloud does not by itself establish that the
summit-to-observer sight line is blocked. Conversely, a thin obstruction directly
on that line may matter much more than its regional coverage.

The maximum-cloud rule, worst-sample rule and distance penalty stack conservative
assumptions. Evaluate them separately. Use reliable cloud-base/altitude information
and observer/summit geometry if available; hourly cloud percentages cannot supply
missing cloud heights. Treat layer weighting as an experimental hypothesis to
evaluate, not a validated replacement formula.

### 3. Make darkness explicit

The current model has no daylight or illumination input. Favorable weather at
midnight can return MOUNTAIN OUT! A future model should expose daylight/observability
separately and define an honest nighttime presentation, such as UNKNOWN with a
darkness explanation. Darkness should not be silently converted to NOT OUT;
moonlit visibility and weather favorability are different questions.

### 4. Improve calibration evidence before changing predictions

Implemented now: successful samples retain the exact selected weather inputs
and the factors that limited the verdict. Corridor diagnostics distinguish local
weather limits from the aggregate distance/visibility penalty. After deploying
the updated backend, new private report snapshots retain these fields using the
existing schema. Previously saved reports cannot recover discarded inputs.

The diagnostic refactor preserves verdicts. A comparison with the prior committed
model matched 4,800 local cases and 1,875 four-sample corridor cases, including
missing samples. Python/JavaScript parity and report-snapshot tests cover the new
fields.

Next: retain a current weather estimate evaluated at report submission alongside
the immutable estimate behind the scanned QR. A QR may be two hours old, while
the form asks for conditions now. Comparing a present observation to an old
display estimate without accounting for that age can mislabel a genuine change
in weather as a prediction failure. Do not overwrite the original snapshot.
Evaluate on later held-out dates/viewpoints and keep disagreement cases, uncertain
answers and report age distinct. Login identifies an account, not a verified
observation or calibration label.

## TRMNL Companion login: what is verified

The official [Companion app source](https://github.com/usetrmnl/trmnl-companion/tree/41cd3663ca77941e0f67563cd345113a604cad9a)
contains an OAuth authorization-code flow:

- [OAuth2Service.swift](https://github.com/usetrmnl/trmnl-companion/blob/41cd3663ca77941e0f67563cd345113a604cad9a/Companion/Services/OAuth2Service.swift)
  redirects to `https://usetrmnl.com/oauth/authorize`, requests the `read` scope,
  validates a random `state`, and exchanges the code at
  `https://usetrmnl.com/api/oauth/token`.
- [APIService.swift](https://github.com/usetrmnl/trmnl-companion/blob/41cd3663ca77941e0f67563cd345113a604cad9a/Companion/Services/APIService.swift)
  uses the access token to fetch the account at `GET https://usetrmnl.com/api/me`.

This establishes a concrete authentication pattern, not permission to reuse that
app's registration, credentials or native-app callback. It also does not establish
that the specific recipe the author saw uses this flow. A name/link for that
recipe remains useful to verify its exact mechanism and reuse terms.

The source app's decoded account type includes email/profile fields but does not
establish a stable opaque account-ID field or OIDC subject. The integration needs
a documented, stable provider account identifier. Do not substitute the access
token, a browser cookie, a user-supplied ID or an unverified client claim for one.

## Proposed mobile submission flow

1. Keep weather polling and artwork public. Scanning a QR opens the observation
   page, preserving the expiring context token across sign-in.
2. A **Sign in with TRMNL** button redirects to our Worker's login endpoint, which
   starts an authorization-code flow using our own registered OAuth client and
   an exact HTTPS callback on the Worker. Bind short-lived, one-use state to the
   browser and use PKCE if the provider supports it. Validate return destinations
   and re-check the QR context after callback so expired links stay expired.
3. Exchange the code on the server, validate the provider account through the
   documented identity endpoint, and issue our own opaque session cookie with
   Secure, HttpOnly and SameSite attributes. Keep provider tokens out of URLs,
   HTML, browser storage and logs. Never copy the reference app's embedded
   credentials or token-request logging. Use minimal approved scopes and discard
   provider tokens after identity validation if no later provider access is needed.
4. Require the server session and existing CSRF protection for POST /feedback.
   Store an HMAC-derived identity from the verified provider identifier, with a
   distinct source/version from old browser hashes. Compute the latest active
   report per account and mountain/viewpoint, preventing cookie resets from
   manufacturing independent votes for that same account. Add per-account and
   service-level rate limits and session expiry/logout handling.
   The public `feedback=true` polling path creates D1 context rows, so it also
   needs a request/issuance limit; authenticating POST alone does not bound that
   unauthenticated write path.
5. Keep the current weather estimate and community observations distinguishable.
   Choose explicitly whether a single authenticated report may override weather;
   account authentication alone is not a reason to call it a verified observation.
   Update privacy/retention text for the new identity processing and decide how
   pre-login anonymous reports are handled during migration.

Companion's own login session is on a different origin; our Worker cannot treat
that cookie or simply opening the app as proof of identity. The browser should
complete a supported redirect flow back to the Worker.

## Prerequisites before implementing login

- Confirm that TRMNL supports a third-party web OAuth client for this use, its
  registration process, allowed scopes, exact endpoints and a stable identifier.
  The current official app is evidence of the flow, not a complete public
  registration contract.
- Register this site's OAuth application and callback. Supply that application's
  credentials securely through Worker/environment settings, never chat, recipe
  templates, a downloaded ZIP or source control. Existing environment metadata
  contains no configured OAuth credentials.
- Permit the approved authorization/token/identity hosts where needed. The
  current cloud environment allows package/GitHub hosts; it does not permit direct
  TRMNL website requests. Configure the needed domain additions without replacing
  an unknown existing allowlist. The production Worker's egress is separate.

Login is not implemented or enabled by this review. Anonymous submission policy
and weather thresholds remain as before; the completed code change adds evidence
needed to evaluate the next model and feedback-policy changes.

## Validation of the prepared change

All 48 Python tests and seven Worker tests passed, including the build dry run,
cross-language parity for input diagnostics and limiting factors, and immutable
evidence in Python/Worker feedback snapshots. The comparison against the previous
commit described above checks verdict preservation separately from those tests.
No live calibration, OAuth sign-in or public deployment was performed.
