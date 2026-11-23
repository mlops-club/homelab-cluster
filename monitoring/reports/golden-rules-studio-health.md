<!-- Purpose: "What this check does" report for the golden-rules-studio-health check, shown in a collapsed row on the status dashboards
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Outside-in health check, every 20 min from Grafana's public probes in Oregon and Ohio.** It reaches Golden Rules Studio the way a reviewer on the internet does: Cloudflare DNS and TLS, the Cloudflare Tunnel, `traefik-public`, then the app.

| # | Step | Request | Passes when |
|---|---|---|---|
| 1 | Ask the app if it is healthy | `GET https://golden-rules-studio.mlops-club.org/api/health` | `200` over valid TLS within 10 s |

Studio depends on **Harbor** (its container image) and **K2** (shown in the rows below on the Studio stack dashboard). **A red bar means** the public path or the app is down; **grey** means no public probe reported. Definition: [checks_studio.tf](${repo}/monitoring/terraform/checks_studio.tf)
