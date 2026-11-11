# Visibility model and submission authentication review

Reviewed November 11, 2026, on the existing shared-Worker review branch. This is
a code and controlled-fixture review, not an evaluation against live observations
or evidence of a deployed change. The production weather model is implemented in
`cloudflare/src/model.js`; `mountain/model.py` is the Python reference, with parity
tests. The anonymous report overrides are implemented by the Worker, not by the
Python development collector.

Implementation follow-up: [experimental model v2 is now the provisional default](model-v2.md), and
new reports retain submission-time forecasts for both versions alongside their
original QR-linked weather estimate. V1 is retained for comparison and rollback;
the provisional switch after user-confirmed webcam mismatches is not validation.
Revision 2.1 additionally addresses the diagnosed mid-cloud false negative and
moderate surface-visibility penalty. The findings below describe the original
v1 review; the linked model guide describes the current rules.

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

Implemented in the v2 follow-up: retain a current weather estimate evaluated at
report submission alongside the immutable estimate behind the scanned QR.
A QR may be two hours old, while
the form asks for conditions now. Comparing a present observation to an old
display estimate without accounting for that age can mislabel a genuine change
in weather as a prediction failure. Do not overwrite the original snapshot.
Evaluate on later held-out dates/viewpoints and keep disagreement cases, uncertain
answers and report age distinct. Login identifies an account, not a verified
observation or calibration label.

## TRMNL Tug login: confirmed OIDC authorization pattern

The author identified the example as [TRMNL Tug](https://trmnl-tug-markh.azurewebsites.net)
and supplied the sign-in button's destination. Its public protocol parameters
establish a more specific and suitable flow than the older Companion app API:

| Parameter | Observed value or purpose |
| --- | --- |
| Authorization endpoint | `https://trmnl.com/oidc/authorize` |
| `response_type` | `code` |
| `scope` | `openid` |
| `redirect_uri` | Tug's own `/auth/callback` |
| `state` | Binds the authorization response to a login attempt |
| `nonce` | Binds the ID token to that attempt |
| `code_challenge_method` | `S256`, with a PKCE challenge |

This is OpenID Connect authorization code with PKCE. Tug's client ID, callback
and temporary login values must not be reused by our app. The flow is a protocol
we can implement independently; no Tug implementation code has been obtained
or copied, and the supplied login attempt was not opened or replayed.

OIDC supplies an authenticated `sub` claim in a validated ID token. Together with
the verified issuer, this is the proposed account identity for reports. It avoids
depending on the older `/api/me` profile response, collecting email, requesting
the broader `read` scope, or asking for an account API key.

Remaining provider details must come from TRMNL's discovery metadata: exact
issuer, token endpoint, signing algorithms, JWKS URI and permitted token-endpoint
client authentication methods. Do not infer them from the authorization URL.
Whether Tug's client is public or confidential is not established by that URL.
An attempted fetch of the conventional public discovery location was denied by
the environment proxy, so no discovery response or token signature was verified.

The official [Companion app source](https://github.com/usetrmnl/trmnl-companion/tree/41cd3663ca77941e0f67563cd345113a604cad9a)
also contains a different, older OAuth flow under `usetrmnl.com/oauth/authorize`
and `api/oauth/token`, using `read` and `/api/me`. That reference is context, not
the integration proposed for this site now that Tug's OIDC route is known.

## Proposed mobile submission flow

1. Keep weather polling and artwork public. Scanning a QR opens the observation
   page, preserving the expiring context token across sign-in.
2. A **Sign in with TRMNL** button redirects to our Worker's login endpoint, which
   starts an OIDC authorization-code flow using our own registered client,
   `scope=openid`, fresh state and nonce, and PKCE S256. Store the verifier and
   short-lived one-use login state on the server, bound to the browser. Use the
   exact registered HTTPS callback on our Worker. Validate return destinations
   and re-check the QR context after callback so expired links stay expired.
3. Exchange the code on the server using our verifier and registered client
   authentication method. Validate the ID token using a maintained OIDC/JWT
   library and the provider's discovery/JWKS: signature, allowed algorithm,
   issuer, audience/authorized party, expiry, nonce and nonempty subject. Never
   treat decoding a JWT as validating it. Issue our own opaque session cookie with
   Secure, HttpOnly and SameSite attributes. Keep provider tokens out of URLs,
   HTML, browser storage and logs. Never copy the reference app's embedded
   credentials or token-request logging. Request only `openid` for identity and
   discard provider tokens after identity validation if no later provider access
   is needed. A refresh token is not necessary for this basic local-session design.
4. Require the server session and existing CSRF protection for POST /feedback.
   Store an HMAC-derived identity from a canonical pair of validated `iss` and
   `sub` claims, with a distinct source/version from old browser hashes. Compute
   the latest active report per account and mountain/viewpoint, preventing cookie resets from
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

TRMNL's own login session is on a different origin; our Worker cannot treat
that cookie or simply opening the app as proof of identity. The browser should
complete a supported redirect flow back to the Worker.

## Prerequisites before implementing login

- Obtain TRMNL's supported registration process and OIDC discovery metadata.
  The Tug launch URL confirms the intended protocol, but not our client
  registration or the provider's complete implementation contract.
- Register this site's own OIDC client and exact callback. Store its client ID
  as configuration and any client secret, if the registered client type requires
  one, securely as a Worker secret. Do not assume PKCE eliminates a confidential
  client's secret, or that a public client needs one. Never share secrets in chat,
  recipe templates, ZIPs or source control. Current environment metadata and
  exported variable names show no OIDC client configuration.
- Permit the approved authorization/token/discovery/JWKS hosts where needed. The
  current cloud environment allows package/GitHub hosts; it does not permit direct
  TRMNL website requests. Configure the needed domain additions without replacing
  an unknown existing allowlist. The production Worker's egress is separate.

Registration brief for TRMNL:

```text
Application: Is the Mountain Out?
Website: https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev
Redirect URI: https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev/auth/callback
Grant type: authorization_code
Response type: code
Scope: openid
PKCE: S256
Purpose: identify accounts submitting mountain observations; no profile/email access needed.
Needed from provider: supported client registration/type, issuer/discovery URL and client ID.
```

Login is not implemented or enabled by this review. Anonymous submission policy
remains in place; subsequent weather-rule changes are documented in the model guide.

## Validation of the prepared change

All 48 Python tests and seven Worker tests passed, including the build dry run,
cross-language parity for input diagnostics and limiting factors, and immutable
evidence in Python/Worker feedback snapshots. The comparison against the previous
commit described above checks verdict preservation separately from those tests.
No live calibration, OIDC sign-in or public deployment was performed.
