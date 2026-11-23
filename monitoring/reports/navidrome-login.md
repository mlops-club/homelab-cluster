<!-- Purpose: "What this check does" report for the navidrome-login check, shown in a collapsed row on the public Homelab status dashboard
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Synthetic login check, every 20 min from the tailnet probe.** It uses the Subsonic API that music apps (Symfonium, play:Sub, the web player) use, as the read-only `homelab-monitor` user, with salted-token auth so the password never crosses the wire. The screenshots show the equivalent screens.

| # | Step | API call | Passes when |
|---|---|---|---|
| 1 | Sign in | `GET /rest/ping` (token + salt) | `status: ok` |
| 2 | Open the library | `GET /rest/getMusicFolders` | at least one folder |
| 3 | Browse albums | `GET /rest/getAlbumList2?type=alphabeticalByName&size=1` | one album |
| 4 | Open the album | `GET /rest/getAlbum` | at least one track |
| 5 | Play a track | `GET /rest/stream?format=raw` with `Range: bytes=0-65535` | `206 Partial Content`, 64 KB read from the NAS |

<img src="${img}/navidrome-1-login.jpg" width="49%"> <img src="${img}/navidrome-2-library.jpg" width="49%">

**A red bar means** Navidrome is down, auth is broken, the library is empty or the NAS mount is not serving audio. Script: [navidrome-login.js](${repo}/monitoring/checks/navidrome-login.js)
