# Put the recipe online with Cloudflare

This is the recommended hosting path. Cloudflare handles HTTPS, the running
application, artwork hosting and persistent D1 storage. No Python server, reverse
proxy, custom domain or server-management commands are needed.

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/nikokoren/is_the_mountain_out)

## Easiest: use the deployment button

1. Click **Deploy to Cloudflare** above and sign in to your existing Cloudflare account.
2. Connect GitHub if Cloudflare asks. The deployment flow creates a copy of this
   repository in your GitHub account. If the original repository name already
   exists there, choose another name, such as `mountain-trmnl-host`.
3. Keep the proposed Worker name, or choose a name you prefer. Allow Cloudflare
   to create the **D1 database** required by the `DB` binding. No API keys need to
   be pasted into the application setup.
4. Keep the detected commands: build **`npm run build`**, deploy **`npm run deploy`**.
   The root directory is the repository root, not `cloudflare/`.
5. Select **Deploy**. When it finishes, open the generated **`.workers.dev`** address.
   The landing page gives you the exact service URL to copy into TRMNL.

The root `wrangler.jsonc` declares the Worker, static artwork, D1 binding and hourly
cleanup. Cloudflare provisions D1; the application creates its initial tables
automatically on its first API request. Keep that database when redeploying.
Do not create an R2 bucket or purchase a domain for this recipe.

The button uses Cloudflare's documented public-repository deployment flow, including
automatic resource provisioning. That account-authorized flow cannot be completed
from this chat without your Cloudflare connection/authorization. It has not been
run against your account yet.

## Alternative: keep deploying the existing repository

If you want commits to `nikokoren/is_the_mountain_out` to deploy automatically:

1. In **Workers & Pages**, choose **Create application** and the option to import
   an existing Git repository.
2. Connect GitHub, select `nikokoren/is_the_mountain_out`, and select branch **main**.
3. Use the repository root, build command **`npm run build`**, and deploy command
   **`npm run deploy`**. Keep the default Node build environment (Node 22+).
4. Approve the D1 resource setup when requested and deploy.

The deployment button creates a separate repository copy; this alternative keeps
the existing repository as the source for future deployments. Choose one route.

If the build specifically reports missing D1 permissions, use Cloudflare's build
token settings to grant **D1 Edit** for this account, then retry the deployment.
Do not post tokens in chat or commit them to Git. If the database exists but `DB`
is unbound, use **Settings → Bindings** to bind that D1 database with the name **DB**.

## Connect TRMNL

In the Private Plugin settings, set **Visibility service URL** to the new HTTPS
origin with no trailing slash. Choose a mountain and its location. Turn on
**Show feedback QR code** if you want community reports.

Use the current files in `plugin/src/` for the polling URL, custom fields, Shared
template and each layout tab. The recipe is pinned to Framework 3.4.0.

Check the deployed site before relying on the device:

- The landing page opens at your `.workers.dev` address.
- `/health` returns `{"status":"ok","storage":"d1"}`.
- `/api/visibility?mountain=rainier&viewpoint=seattle` returns a current result.
  UNKNOWN means the weather data is missing/stale, not that the mountain is hidden.
- The QR feedback page names the correct mountain and viewpoint. Submit an actual
  observation, then confirm the receipt and subsequent display refresh.

The free Workers/D1 allowances are intended for this small pilot, but are not
unlimited. Check Cloudflare's current limits and the usage shown in your account;
this configuration does not subscribe you to a paid plan or enable paid services.
Open-Meteo access is cached for 15 minutes per coordinate. The scope of any
TRMNL/Open-Meteo agreement has not been verified; this Worker makes direct requests
to the public endpoint. It does not assume TRMNL's commercial entitlement transfers
to third-party hosting. Attribution is on the landing page and API.

## How votes work in the hosted version

- A report counts for **20 minutes from submission**, for its mountain/viewpoint.
- Only the latest report per anonymous browser counts. A newer report replaces its
  prior active vote; changing to **Can't tell** withdraws the previous condition.
- Replaying the same form with the same answer does not extend its lifetime.
- Out, partly out and not out map to the corresponding display illustrations.
- Conflicting current answers produce **UNKNOWN**. There is no majority override.
- When no informative votes remain, the weather estimate resumes.
- API fields `display_basis`, `source`, `reported_at`, `reports_expire_at`,
  `report_count` and `weather_estimate` distinguish reports from forecasts. A QR
  page describes the source and limits; the minimal display still shows the
  mountain and verdict only.
- A 15-minute device refresh means reports can take up to 15 minutes to appear,
  and a report used just before expiry can remain on a physical screen until
  nearly **35 minutes after submission**. A missed refresh may retain it longer.

No accounts or invitations are required under the initial trust policy. A browser
cookie is not proof of identity, and the QR can be shared. Adjust abuse handling
if the pilot exposes a problem. No names, GPS or raw IP addresses are stored by
the application; Cloudflare maintains its own platform-level operational data.

## Review and retention

In Cloudflare's D1 database console, this query shows report history without
anonymous browser identifiers:

```sql
SELECT id, datetime(received, 'unixepoch') AS received_utc,
       mountain, viewpoint, answer,
       json_extract(snapshot, '$.status') AS predicted_status,
       json_extract(snapshot, '$.forecast_at') AS forecast_at
FROM reports ORDER BY received DESC LIMIT 100;
```

Review disagreement cases early in the pilot. Compare timestamps and viewpoint
before attributing a difference to a model error. Keep uncertainty and conflicting
answers visible; don't claim calibrated probabilities from a small group.

The hourly scheduled task deletes expired two-hour QR contexts, weather cache older
than a day, and report history older than 90 days. No raw-report export is exposed
on the public website. Preserve the D1 database across deployments and apply the
same retention policy to exports/backups. The Python development server's SQLite
database is separate; existing local data is not silently migrated into D1.

## Development checks

From the repository root, with Node 22+ and Python 3.11+ available:

```sh
npm ci
npm test
npm run dev
```

`npm test` first performs a deployment dry run, then checks weather-model parity
with Python and exercises the Worker/D1 runtime with controlled weather. It tests
report replacement, independent expiry, conflicting reports, unknown weather,
forms, CSRF protection, QR links and route isolation. External weather requests
are blocked by the integration test, so tests do not prove live provider access.

The Python server remains a local development/reference implementation. Its
collector stores and compares reports but does not override weather verdicts;
the hosted Worker implements the agreed community-vote policy.
