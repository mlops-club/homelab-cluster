# Monitoring Accounts and Credentials

**Purpose**: Inventory of every login, token and webhook the homelab monitoring stack uses, with no secret values

**Scope**: Grafana Cloud stack, Synthetic Monitoring, the per-app monitoring users, alert delivery, and the
    admin credentials used to create them

**Overview**: Each row names the account, what it can do, where its secret lives, and what reads it. Secrets
    live in `~/credentials/*.env` (mode 600) or the repo `.env` (gitignored), never in git. Terraform reads
    them through `monitoring/terraform/tf`. Rotation steps are at the end.

**Related**: [ADR 0001 Grafana POC](adr/0001-outside-in-monitoring/grafana-poc.md),
    `monitoring/terraform/`, `monitoring/checks/`

---

## Where secrets live

| File | Holds | Read by |
|---|---|---|
| `.env` (repo root, gitignored) | `GRAFANA_URL`, `GRAFANA_STACK_ID`, `GRAFANA_SM_URL`, `GRAFANA_SA_TOKEN`, `GRAFANA_SM_TOKEN` | `monitoring/terraform/tf`, `monitoring/scripts/*` |
| `~/credentials/homelab-monitoring.env` | URL, username and password of each monitoring user | `tf` (writes the passwords into Grafana secrets), local `k6 run` |
| `~/credentials/homelab-alerting.env` | `DISCORD_ALERTS_WEBHOOK_URL` | `tf` (Discord contact point) |
| `~/credentials/.env` | `ABS_URL`, `ABS_API_TOKEN` (Audiobookshelf root API key `eric-automation`) | Admin scripts |
| `monitoring/terraform/terraform.tfstate` (gitignored) | Probe token, MCP token, public status link, Discord webhook | `./tf output -raw <name>` |

## Grafana Cloud

| Account | Role | Secret location | Used by |
|---|---|---|---|
| Stack `gallantfudge2729` owner | Grafana Cloud org admin | Owner's password manager | Humans only |
| Service account `homelab-terraform` | Admin | `.env` `GRAFANA_SA_TOKEN` | Terraform, `promql`, `alert-states` |
| Synthetic Monitoring access token | Synthetics API | `.env` `GRAFANA_SM_TOKEN` | Terraform (probes, checks) |
| Private probe `homelab-tailnet-laptop` | Runs checks, pushes results | tfstate output `tailnet_laptop_probe_token` | Podman container `homelab-sm-agent` (`API_TOKEN`) |
| Service account `homelab-mcp` | Viewer (read-only) | tfstate output `mcp_token` | `mcp-grafana` for Claude Code |
| Public dashboard "Homelab status" | Anonymous read of 3 panels | tfstate output `status_page_path` | Status-page viewers; the link works as a bearer secret |

## Monitoring users (login smoke tests)

Each app has a dedicated `homelab-monitor` account with the least privilege that still lets it log in,
browse and read a byte range of real media. The k6 scripts read passwords from Grafana's secret store
(`await secrets.get('<app>-monitor-password')`). Terraform fills the store from `homelab-monitoring.env`
through a write-only argument, so passwords stay out of Terraform state.

| App | Login | Permissions | Grafana secret | Check (probe) |
|---|---|---|---|---|
| Jellyfin | `homelab-monitor` | Not admin, hidden from the login screen; playback allowed; no delete, download, transcode, sharing or remote control; never locked out | `jellyfin-monitor-password` | `jellyfin-login` (tailnet) |
| Navidrome | `homelab-monitor` | Not admin | `navidrome-monitor-password` | `navidrome-login` (tailnet) |
| Immich | `homelab-monitor@mlops-club.org` | Not admin, 0-byte quota; owns one generated canary image (`homelab-monitor-canary.png`) so no personal photos are read | `immich-monitor-password` | `immich-login` (tailnet) |
| Audiobookshelf | `homelab-monitor` | Guest: stream only; no download, upload, edit or delete | `audiobookshelf-monitor-password` | `audiobookshelf-login` (Oregon, Ohio, via `books.mlops-club.org`) |

## Alert delivery

| Channel | Identity | Secret location | Routing |
|---|---|---|---|
| Discord `#homelab-alerts` | Webhook `homelab-monitor` | `~/credentials/homelab-alerting.env` | Contact point `homelab-discord`; only alerts labelled `team=homelab` |

## Admin credentials used to create the monitoring users

| App | How admin access was obtained |
|---|---|
| Jellyfin, Navidrome | Owner's signed-in admin browser session |
| Immich | Owner's admin account; password reset with `kubectl -n immich exec -it deploy/immich-server -- immich-admin reset-admin-password` |
| Audiobookshelf | Root API key `ABS_API_TOKEN` in `~/credentials/.env` |

## Rotation

| Secret | Steps |
|---|---|
| Monitoring-user password | Change it in the app (admin UI), update `homelab-monitoring.env`, then `./tf apply -replace='grafana_apps_secret_securevalue_v1beta1.monitor_password["<app>"]'` |
| `GRAFANA_SA_TOKEN` | Grafana → Administration → Service accounts → `homelab-terraform` → add token, update `.env`, delete the old token |
| `GRAFANA_SM_TOKEN` | Synthetics → Config → Access tokens → generate, update `.env` |
| Probe token | `./tf apply -replace=grafana_synthetic_monitoring_probe.tailnet_laptop`, then recreate the agent container with the new `API_TOKEN` |
| MCP token | `./tf apply -replace=grafana_service_account_token.mcp` |
| Public status link | `./tf apply -replace=grafana_dashboard_public.status` |
| Discord webhook | Discord → channel settings → Integrations → Webhooks → delete and recreate, update `homelab-alerting.env`, `./tf apply` |
