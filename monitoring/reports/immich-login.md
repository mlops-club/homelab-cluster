<!-- Purpose: "What this check does" report for the immich-login check, shown in a collapsed row on the public Homelab status dashboard
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Synthetic login check, every 20 min from the tailnet probe.** It makes the same API calls the Immich web and mobile apps make, as `homelab-monitor@mlops-club.org`. That user owns a single generated canary image, so the check never opens personal photos. The screenshots show the equivalent screens.

| # | Step | API call | Passes when |
|---|---|---|---|
| 1 | Sign in | `POST /api/auth/login` | 201 with an access token |
| 2 | Open the timeline | `POST /api/search/metadata` | the canary photo is found |
| 3 | Show the thumbnail | `GET /api/assets/{id}/thumbnail?size=preview` | image bytes (thumbnail pipeline works) |
| 4 | Open the original | `GET /api/assets/{id}/original` with `Range: bytes=0-65535` | `206 Partial Content`, read from the NAS |
| 5 | Sign out | `POST /api/auth/logout` | (cleanup) |

<img src="${img}/immich-1-login.jpg" width="49%"> <img src="${img}/immich-2-library.jpg" width="49%">

**A red bar means** Immich is down, login or search is broken, thumbnails are missing, or the NAS mount is not serving originals. Script: [immich-login.js](${repo}/monitoring/checks/immich-login.js)
