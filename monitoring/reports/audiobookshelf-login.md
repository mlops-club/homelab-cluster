<!-- Purpose: "What this check does" report for the audiobookshelf-login check, shown in a collapsed row on the public Homelab status dashboard
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Synthetic login check, every 20 min from Grafana's Oregon and Ohio probes.** It goes through the public internet path listeners use (Cloudflare, the tunnel, Traefik) to `books.mlops-club.org`. It makes the same API calls the web player and AudioBooth make, as the `homelab-monitor` guest user, which can stream but not download, upload or edit. The screenshots show the equivalent screens.

| # | Step | API call | Passes when |
|---|---|---|---|
| 1 | Sign in | `POST /login` | 200 with a user |
| 2 | Open the bookshelf | `GET /api/libraries` | at least one library |
| 3 | Pick a book | `GET /api/libraries/{id}/items?limit=1&sort=addedAt` | one book |
| 4 | Open the book | `GET /api/items/{id}?expanded=1` | at least one audio file |
| 5 | Press play | `GET /api/items/{id}/file/{ino}` with `Range: bytes=0-65535` | `206 Partial Content`, 64 KB read from the NAS |
| 6 | Sign out | `POST /logout` | (cleanup) |

<img src="${img}/audiobookshelf-1-login.jpg" width="49%"> <img src="${img}/audiobookshelf-2-library.jpg" width="49%">

**A red bar means** listeners can't sign in or play from outside the house. If this row is red but the private checks are green, suspect Cloudflare or the tunnel. Script: [audiobookshelf-login.js](${repo}/monitoring/checks/audiobookshelf-login.js)
