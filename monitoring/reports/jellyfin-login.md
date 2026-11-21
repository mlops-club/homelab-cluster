<!-- Purpose: "What this check does" report for the jellyfin-login check, shown in a collapsed row on the public Homelab status dashboard
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Synthetic login check, every 15 min from the tailnet probe.** It makes the same API calls the Jellyfin web and TV apps make, as the read-only `homelab-monitor` user. It does not click the UI; the screenshots show the equivalent screens.

| # | Step | API call | Passes when |
|---|---|---|---|
| 1 | Sign in | `POST /Users/AuthenticateByName` | 200 with an access token |
| 2 | Open the home screen | `GET /Users/{id}/Views` | at least one library |
| 3 | Pick a title | `GET /Items?Recursive=true&SortBy=DateCreated&Limit=1` | one movie, episode or song |
| 4 | Start playback | `GET /Videos/{id}/stream?static=true` with `Range: bytes=0-65535` | `206 Partial Content`, 64 KB read from the NAS |
| 5 | Sign out | `POST /Sessions/Logout` | (cleanup) |

<img src="${img}/jellyfin-1-login.jpg" width="49%"> <img src="${img}/jellyfin-2-library.jpg" width="49%">

**A red bar means** one of steps 1–4 failed: Jellyfin down, login broken, library database unreadable, or the NAS mount not serving files. Script: [jellyfin-login.js](${repo}/monitoring/checks/jellyfin-login.js)
