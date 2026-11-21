# Purpose: Status dashboard shared by public link, standing in for a status page
# Scope: Grafana POC test 7. Read-only, no variables (public dashboards don't support them)
# Overview: One row per listener-facing service. Left: current state (UP / DOWN / NO DATA) and 24 h uptime.
#   Right: one bar per check run, height = how long the run took; green passed, red failed, grey = no
#   result arrived (probe, network or Grafana problem). Missing data never reads as healthy. Under each
#   service, a collapsed row holds a step-by-step report (monitoring/reports/<job>.md) with screenshots
#   served from the public GitHub repo

locals {
  status_services = [
    { name = "Jellyfin", job = "jellyfin-login", every = "15m" },
    { name = "Navidrome", job = "navidrome-login", every = "15m" },
    { name = "Photos (Immich)", job = "immich-login", every = "15m" },
    { name = "Audiobookshelf", job = "audiobookshelf-login", every = "15m" },
    { name = "Audiobookshelf page load (Oregon, Ohio)", job = "audiobookshelf-browser", every = "15m" },
  ]
  prom  = { type = "prometheus", uid = "grafanacloud-prom" }
  row_h = 6
  block = local.row_h + 2 # service row header + panels + collapsed report row
  # Screenshots and links point at the public repo; switch docs_ref to "main" once the PR merges
  docs_ref = "docs/adr-outside-in-monitoring"
  repo_url = "https://github.com/mlops-club/homelab-cluster/blob/${local.docs_ref}"
  img_url  = "https://raw.githubusercontent.com/mlops-club/homelab-cluster/${local.docs_ref}/.ai/docs/adr/0001-outside-in-monitoring/images/grafana-poc/steps"
  state_map = [{ type = "value", options = {
    "-1" = { text = "NO DATA", color = "#6e6e6e", index = 0 }
    "0"  = { text = "DOWN", color = "red", index = 1 }
    "1"  = { text = "UP", color = "green", index = 2 }
  } }]

  status_panels = flatten([for i, s in local.status_services : [
    { id = i * 10 + 5, type = "row", title = s.name, collapsed = false, panels = [], gridPos = { x = 0, y = i * local.block, w = 24, h = 1 } },
    {
      id      = i * 10 + 1, type = "stat", title = "${s.name}: now", datasource = local.prom
      gridPos = { x = 0, y = i * local.block + 1, w = 5, h = 3 }
      targets = [{ refId = "A", instant = true,
        # last result within ~1.3 check intervals; nothing at all means the probe or network is down
      expr = "min(last_over_time(probe_success{job=\"${s.job}\"}[20m])) or on() vector(-1)" }]
      options     = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { mappings = local.state_map } }
    },
    {
      id      = i * 10 + 2, type = "stat", title = "${s.name}: uptime, 24 h", datasource = local.prom
      gridPos = { x = 0, y = i * local.block + 4, w = 5, h = 3 }
      targets = [{ refId = "A", instant = true,
      expr = "avg(avg_over_time(probe_success{job=\"${s.job}\"}[24h]))" }]
      options = { colorMode = "value", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "percentunit", decimals = 2, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "red", value = null }, { color = "orange", value = 0.99 }, { color = "green", value = 0.999 }] } } }
    },
    {
      id       = i * 10 + 3, type = "timeseries", title = "${s.name}: time per check run", datasource = local.prom
      gridPos  = { x = 5, y = i * local.block + 1, w = 19, h = local.row_h }
      interval = s.every # one bar per check run
      targets = [
        { refId = "A", legendFormat = "Passed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 1)" },
        { refId = "B", legendFormat = "Failed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 0)" },
        { refId = "C", legendFormat = "No result",
        expr = "(vector(0.5) unless on() count(count_over_time(probe_success{job=\"${s.job}\"}[20m]))) and on() (count(count_over_time(probe_success{job=\"${s.job}\"}[30d])) > 0)" },
      ]
      options = { legend = { showLegend = true, displayMode = "list", placement = "bottom" }, tooltip = { mode = "multi" } }
      fieldConfig = {
        defaults = { unit = "s", min = 0, custom = { drawStyle = "bars", fillOpacity = 90, lineWidth = 0, barAlignment = 0,
        barWidthFactor = 0.7, showPoints = "never", spanNulls = false, stacking = { mode = "none" } } }
        overrides = [for o in [["Passed", "green"], ["Failed", "red"], ["No result", "#6e6e6e"]] :
        { matcher = { id = "byName", options = o[0] }, properties = [{ id = "color", value = { mode = "fixed", fixedColor = o[1] } }] }]
      }
    },
    {
      id      = i * 10 + 6, type = "row", title = "${s.name}: what this check does (click to expand)", collapsed = true
      gridPos = { x = 0, y = i * local.block + 1 + local.row_h, w = 24, h = 1 }
      panels = [{
        id      = i * 10 + 4, type = "text", title = "", transparent = true
        gridPos = { x = 0, y = i * local.block + 2 + local.row_h, w = 24, h = 17 }
        options = { mode = "markdown", content = templatefile("${path.module}/../reports/${s.job}.md", { img = local.img_url, repo = local.repo_url }) }
      }]
    },
  ]])
}

resource "grafana_dashboard" "status" {
  config_json = jsonencode({
    title    = "Homelab status"
    uid      = "homelab-status"
    refresh  = "1m"
    time     = { from = "now-24h", to = "now" }
    timezone = "browser"
    panels   = local.status_panels
  })
}

resource "grafana_dashboard_public" "status" {
  dashboard_uid          = grafana_dashboard.status.uid
  is_enabled             = true
  share                  = "public"
  time_selection_enabled = false
  annotations_enabled    = false
}

output "status_page_path" {
  description = "Append to GRAFANA_URL; anyone with the link can view, so treat it as a secret"
  sensitive   = true
  value       = "/public-dashboards/${grafana_dashboard_public.status.access_token}"
}
