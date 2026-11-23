<!-- Purpose: "What this check does" report for the harbor-health check, shown in a collapsed row on the status dashboards
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Health check, every 20 min from the in-cluster probe (`homelab-cluster`, over the tailnet).** Harbor is the private container registry at `cr.priv.mlops-club.org`; every app image, including Golden Rules Studio's, is pulled from it.

| # | Step | Request | Passes when |
|---|---|---|---|
| 1 | Ask Harbor for its component health | `GET https://cr.priv.mlops-club.org/api/v2.0/health` | `200` over valid TLS within 5 s |

**A red bar means** Harbor's API is down or unhealthy, so new pods can't pull images (running pods keep working). Definition: [checks_health.tf](${repo}/monitoring/terraform/checks_health.tf)
