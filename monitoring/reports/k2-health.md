<!-- Purpose: "What this check does" report for the k2-health check, shown in a collapsed row on the status dashboards
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Health check, every 5 min from the in-cluster probe (`homelab-cluster`, over the tailnet).** K2 runs in the cluster at `k2.priv.mlops-club.org` and is part of the Golden Rules Studio stack.

| # | Step | Request | Passes when |
|---|---|---|---|
| 1 | Ask K2 if it is healthy | `GET https://k2.priv.mlops-club.org/health` | `200` over valid TLS within 5 s |

**A red bar means** K2 or its route through `traefik-private` is down. Definition: [checks_health.tf](${repo}/monitoring/terraform/checks_health.tf)
