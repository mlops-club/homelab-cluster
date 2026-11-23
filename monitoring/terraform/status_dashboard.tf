# Purpose: Status dashboards: an internal one for everyone who runs the cluster, an external one for Studio users
# Scope: Two dashboards from one panel recipe. "Homelab status" (internal): every monitored service, with
#   per-check reports that name hosts, routes and code. "Golden Rules Studio status" (external): Golden Rules Studio
#   plus the two services it depends on, Harbor and K2, written for someone who only cares whether it is up: no
#   links to the repo, no hostnames, no infrastructure names, no run log (its error lines can carry hostnames).
#   Read-only, no variables (public dashboards don't support them)
# Overview: A collapsed "How uptime is calculated" row at the top: a table of each service's readings, uptime,
#   downtime and how much of the 14-day window is measured so far, then three formula cards stacked under it.
#   No targets or verdicts are shown. Below it, one row per service. Left: current state (UP / DOWN / NO DATA) and
#   24 h uptime. Right: one bar per check run, height = how long the run took; green passed, red failed, grey = no
#   result arrived. Missing data never reads as healthy. Under each service, a collapsed row explains the check, then
#   compares the selected period with the 24 h before it (status_selection.tf); internally it also has the run log

locals {
  check_every = "20m" # every check runs every 20 minutes (checks_*.tf); one bar per run
  # locs: probe locations running the check; report_h: height of the internal report text panel;
  # slo: key in local.slo_services (slos.tf), or null; about: plain-language description for the external dashboard
  status_services = [
    { name = "Jellyfin", job = "jellyfin-login", locs = 1, report_h = 21, slo = "jellyfin", about = null },
    { name = "Navidrome", job = "navidrome-login", locs = 1, report_h = 21, slo = "navidrome", about = null },
    { name = "Photos (Immich)", job = "immich-login", locs = 1, report_h = 21, slo = "immich", about = null },
    { name = "Audiobookshelf", job = "audiobookshelf-login", locs = 2, report_h = 21, slo = "audiobookshelf", about = null },
    { name = "Audiobookshelf page load (Oregon, Ohio)", job = "audiobookshelf-browser", locs = 2, report_h = 21, slo = null, about = null },
    { name = "Golden Rules Studio", job = "golden-rules-studio-health", locs = 2, report_h = 9, slo = "golden-rules-studio",
    about = "**Every 20 minutes, from two places on the public internet (Oregon and Ohio),** a monitor opens Golden Rules Studio's health page the way your browser opens the app. A run passes when the app answers \"healthy\" within 10 seconds over a valid secure connection.\n\nStudio depends on the two services below it. **A red bar** means Studio could not be reached or reported a problem; **grey** means no result arrived, which also counts as down." },
    { name = "Harbor (container registry)", job = "harbor-health", locs = 1, report_h = 9, slo = "harbor",
    about = "**Every 20 minutes,** a monitor asks Harbor, the registry that stores Studio's software, whether it is healthy. A run passes when it answers \"healthy\" within 5 seconds.\n\n**A red bar** means the registry is down. Studio keeps running while it is down, but updates to Studio can't be delivered." },
    { name = "K2", job = "k2-health", locs = 1, report_h = 9, slo = "k2",
    about = "**Every 20 minutes,** a monitor asks K2, a service Studio depends on, whether it is healthy. A run passes when it answers \"healthy\" within 5 seconds.\n\n**A red bar** means K2 is down or unreachable." },
  ]
  status_dashboards = {
    status = { title = "Homelab status", uid = "homelab-status", internal = true, jobs = [for s in local.status_services : s.job] }
    studio = {
      title = "Golden Rules Studio status", uid = "studio-stack-status", internal = false
      jobs  = ["golden-rules-studio-health", "harbor-health", "k2-health"]
    }
  }

  prom  = { type = "prometheus", uid = "grafanacloud-prom" }
  row_h = 6
  # Internal reports link to the public repo; switch docs_ref to "main" once the PR merges
  docs_ref = "docs/adr-outside-in-monitoring"
  repo_url = "https://github.com/mlops-club/homelab-cluster/blob/${local.docs_ref}"
  raw_url  = "https://raw.githubusercontent.com/mlops-club/homelab-cluster/${local.docs_ref}/.ai/docs/adr/0001-outside-in-monitoring/images"
  img_url  = "${local.raw_url}/grafana-poc/steps"
  state_map = [{ type = "value", options = {
    "-1" = { text = "NO DATA", color = "#6e6e6e", index = 0 }
    "0"  = { text = "DOWN", color = "red", index = 1 }
    "1"  = { text = "UP", color = "green", index = 2 }
  } }]

  # ---- "How uptime is calculated" row (top of each dashboard) ----
  math_row_h = 1
  # Formula cards are embedded in the dashboard (no outside image host, so the external dashboard links nowhere).
  # Rendered by ../dashboard-images/render.js; 1.5x, 16-colour PNGs. One text panel per card: Grafana truncates a
  # text panel's content at about 100k characters. h = grid rows for the card shown 760 px wide
  math_cards = [for c in [{ n = "uptime-1-formula", h = 15 }, { n = "uptime-2-downtime", h = 12 }, { n = "uptime-3-missing", h = 12 }] :
  merge(c, { img = "<img src=\"data:image/png;base64,${filebase64("${path.module}/../dashboard-images/${c.n}.png")}\" width=\"760\">" })]
  math_text = { for d, dash in local.status_dashboards : d => join("\n\n", concat([
    "**Uptime** is the share of readings that were up over the last ${trimsuffix(local.slo_window, "d")} days. Every 5 minutes, each check location gives one reading: **up** if its latest check result passed, **down** if it failed or if no result arrived, so silence never looks healthy. Monitoring began recently, so until 14 days are recorded, the numbers cover only the days measured (last column of the table). The cards below walk through each formula: first in words, then with an example's numbers.",
    ], dash.internal ? ["Code: readings and the 14-day window in [slos.tf](${local.repo_url}/monitoring/terraform/slos.tf), this table and the cards in [status_dashboard.tf](${local.repo_url}/monitoring/terraform/status_dashboard.tf). Background: [ADR 0001](${local.repo_url}/.ai/docs/adr/0001-outside-in-monitoring/decision.md)."] : []
  )) }
  math_table_h = { for d, dash in local.status_dashboards : d => length([for s in local.status_services : s if s.slo != null && contains(dash.jobs, s.job)]) + 2 }
  math_text_h  = { for d, dash in local.status_dashboards : d => dash.internal ? 3 : 2 }
  # One query per table column, one series per service (label `service`), from Grafana SLO's own 5-minute
  # recording rules: success = readings up per bucket, total = readings expected per bucket (slos.tf). The
  # recording rules exist only since each service's SLO was created, so these count the measured days only
  window_sub = "[${local.slo_window}:5m]"
  readings_col = {
    expected = "sum_over_time((grafana_slo_total_rate_5m{grafana_slo_uuid=\"UUID\"} < +Inf)${local.window_sub})"
    up       = "sum_over_time((grafana_slo_success_rate_5m{grafana_slo_uuid=\"UUID\"} < +Inf)${local.window_sub})"
  }
  uptime_cols = {
    EXPECTED = "(${local.readings_col.expected})"
    UP       = "(${local.readings_col.up})"
    DOWN     = "(${local.readings_col.expected} - ${local.readings_col.up})"
    UPTIME   = "(${local.readings_col.up} / ${local.readings_col.expected})"
    DOWNTIME = "((${local.readings_col.expected} - ${local.readings_col.up}) * 300 / LOCS)" # seconds
    DAYS     = "(${local.readings_col.expected} / (LOCS * 288))"                            # 288 readings per day
  }
  uptime_targets = { for d, dash in local.status_dashboards : d => {
    for col, tmpl in local.uptime_cols : col => join(" or ", [for s in local.status_services :
      "label_replace(sum(${replace(replace(tmpl, "UUID", grafana_slo.availability[s.slo].id), "LOCS", s.locs)}), \"service\", \"${s.name}\", \"\", \"\")"
    if s.slo != null && contains(dash.jobs, s.job)])
  } }
  uptime_col_order = ["EXPECTED", "UP", "DOWN", "UPTIME", "DOWNTIME", "DAYS"]
  uptime_col_names = {
    EXPECTED = "Readings expected", UP = "Readings up", DOWN = "Readings down",
    UPTIME   = "Uptime", DOWNTIME = "Downtime", DAYS = "Days measured"
  }
  math_panels = { for d, dash in local.status_dashboards : d => [
    {
      id      = 901, type = "row", title = "How uptime is calculated (click to expand)", collapsed = true
      gridPos = { x = 0, y = 0, w = 24, h = 1 }
      panels = concat([
        {
          id      = 903, type = "table", datasource = local.prom
          title   = "Last ${trimsuffix(local.slo_window, "d")} days, or since monitoring began. One reading = one location's latest result, every 5 minutes; no result counts as down"
          gridPos = { x = 0, y = 1, w = 24, h = local.math_table_h[d] }
          targets = [for col in local.uptime_col_order :
          { refId = col, instant = true, format = "table", expr = local.uptime_targets[d][col] }]
          transformations = [
            { id = "merge", options = {} },
            { id = "organize", options = {
              excludeByName = { Time = true }
              indexByName   = merge({ service = 0 }, { for i, c in local.uptime_col_order : "Value #${c}" => i + 1 })
              renameByName  = merge({ service = "Service" }, { for c in local.uptime_col_order : "Value #${c}" => local.uptime_col_names[c] })
            } },
          ]
          fieldConfig = {
            defaults = { decimals = 0 }
            overrides = [
              { matcher = { id = "byName", options = "Uptime" }, properties = [{ id = "unit", value = "percentunit" }, { id = "decimals", value = 2 }] },
              { matcher = { id = "byName", options = "Downtime" }, properties = [{ id = "unit", value = "dtdurations" }] },
              { matcher = { id = "byName", options = "Days measured" }, properties = [
              { id = "decimals", value = 1 }, { id = "unit", value = "suffix: of ${trimsuffix(local.slo_window, "d")}" }] },
            ]
          }
        },
        {
          id      = 902, type = "text", title = "", transparent = true
          gridPos = { x = 0, y = 1 + local.math_table_h[d], w = 24, h = local.math_text_h[d] }
          options = { mode = "markdown", content = local.math_text[d] }
        },
        ], [for i, c in local.math_cards : {
          id      = 904 + i, type = "text", title = "", transparent = true
          gridPos = { x = 0, y = 1 + local.math_table_h[d] + local.math_text_h[d] + sum(concat([0], [for j, o in local.math_cards : o.h if j < i])), w = 24, h = c.h }
          options = { mode = "markdown", content = c.img }
      }])
    },
  ] }

  # ---- one block of rows per service ----
  dash_services = { for d, dash in local.status_dashboards : d => [for s in local.status_services : s if contains(dash.jobs, s.job)] }
  report_h      = { for d, dash in local.status_dashboards : d => { for s in local.status_services : s.job => dash.internal ? s.report_h : 5 } }
  service_panels = { for d, services in local.dash_services : d => flatten([for i, s in services : [
    { id = i * 10 + 5, type = "row", title = s.name, collapsed = false, panels = [], gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2), w = 24, h = 1 } },
    {
      id       = i * 10 + 1, type = "stat", title = "${s.name}: now", datasource = local.prom
      gridPos  = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 1, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true # always "now", whatever is selected
      targets = [{ refId = "A", instant = true,
        # latest result within the last 25 min (one 20-minute run plus slack); nothing at all means no result arrived
      expr = "min(last_over_time(probe_success{job=\"${s.job}\"}[25m])) or on() vector(-1)" }]
      options     = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { mappings = local.state_map } }
    },
    {
      id       = i * 10 + 2, type = "stat", title = "${s.name}: uptime, 24 h (no data = down)", datasource = local.prom
      gridPos  = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 4, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true
      targets = [{ refId = "A", instant = true,
        # same readings as the uptime table (slos.tf): 5-minute readings with no result count as down; readings from before
        # the check's first-ever result are left out, so a new check doesn't start near 0 %
      expr = "${format(local.readings_up, s.job, "24h")} / sum_over_time((vector(${s.locs}) and on() (count(count_over_time(probe_success{job=\"${s.job}\"}[30d])) > 0))[24h:5m])" }]
      options = { colorMode = "value", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "percentunit", decimals = 2, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "red", value = null }, { color = "orange", value = 0.95 }, { color = "green", value = 0.99 }] } } }
    },
    {
      id       = i * 10 + 3, type = "timeseries", title = "${s.name}: time per check run", datasource = local.prom
      gridPos  = { x = 5, y = local.math_row_h + i * (local.row_h + 2) + 1, w = 19, h = local.row_h }
      interval = local.check_every # one bar per check run
      targets = [
        { refId = "A", legendFormat = "Passed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 1)" },
        { refId = "B", legendFormat = "Failed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 0)" },
        { refId = "C", legendFormat = "No result",
        expr = "(vector(0.5) unless on() count(count_over_time(probe_success{job=\"${s.job}\"}[25m]))) and on() (count(count_over_time(probe_success{job=\"${s.job}\"}[30d])) > 0)" },
      ]
      options = { legend = { showLegend = true, displayMode = "list", placement = "bottom" }, tooltip = { mode = "single" } }
      fieldConfig = {
        defaults = { unit = "s", min = 0,
          # Click a bar: select that run (the 30 min around the bar always hold it); the toggle below follows it.
          # Signed-in dashboard only: public dashboards hide data links (drag across a bar there instead).
          # One-click: clicking a bar follows this link directly, no menu
          links = [
            { title = local.status_dashboards[d].internal ? "Select this run (log in the toggle below)" : "Select this run", url = "/d/${local.status_dashboards[d].uid}/x?time=$${__value.time}&time.window=1800000", oneClick = true },
          ]
          custom = { drawStyle = "bars", fillOpacity = 90, lineWidth = 0, barAlignment = 0,
        barWidthFactor = 0.7, showPoints = "never", spanNulls = false, stacking = { mode = "none" } } }
        overrides = [for o in [["Passed", "green"], ["Failed", "red"], ["No result", "#6e6e6e"]] :
        { matcher = { id = "byName", options = o[0] }, properties = [{ id = "color", value = { mode = "fixed", fixedColor = o[1] } }] }]
      }
    },
    {
      id      = i * 10 + 6, type = "row", title = "${s.name}: how this check works (click to expand)", collapsed = true
      gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 1 + local.row_h, w = 24, h = 1 }
      panels = concat([{
        id      = i * 10 + 4, type = "text", title = "", transparent = true
        gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 2 + local.row_h, w = 24, h = local.report_h[d][s.job] }
        # internal: the step-by-step report (hosts, routes, code links); external: the plain-language `about`
        options = { mode = "markdown", content = local.status_dashboards[d].internal ? templatefile("${path.module}/../reports/${s.job}.md", { img = local.img_url, repo = local.repo_url }) : s.about }
        }, {
        id      = i * 10 + 8, type = "table", datasource = local.prom
        title   = "Selected period vs the 24 h up to it (average seconds). Drag across the bars to pick a period (one bar = one run)"
        gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 2 + local.report_h[d][s.job] + local.row_h, w = 24, h = 7 }
        targets = [
          { refId = "A", instant = true, format = "table", expr = local.compare_expr[s.job].selected },
          { refId = "B", instant = true, format = "table", expr = local.compare_expr[s.job].baseline },
          { refId = "C", instant = true, format = "table",
          expr = "(${local.compare_expr[s.job].selected} - ${local.compare_expr[s.job].baseline}) / ${local.compare_expr[s.job].baseline}" },
        ]
        transformations = [
          { id = "merge", options = {} },
          { id = "organize", options = {
            excludeByName = { Time = true }
            indexByName   = { item = 0, "Value #A" = 1, "Value #B" = 2, "Value #C" = 3 }
            renameByName  = { item = "Measure", "Value #A" = "Selected period", "Value #B" = "24 h up to it", "Value #C" = "Change" }
          } },
        ]
        fieldConfig = {
          defaults = { unit = "s", decimals = 2 }
          overrides = [{ matcher = { id = "byName", options = "Change" }, properties = [
            { id = "unit", value = "percentunit" }, { id = "decimals", value = 0 },
            { id = "custom.cellOptions", value = { type = "color-text" } },
            { id = "thresholds", value = { mode = "absolute", steps = [
            { color = "green", value = null }, { color = "orange", value = 0.15 }, { color = "red", value = 0.5 }] } },
          ] }]
        }
        }], [for p in [{
          id      = i * 10 + 7, type = "logs", title = "${s.name}: run log for the selected period (newest first)", datasource = local.logs
          gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 9 + local.report_h[d][s.job] + local.row_h, w = 24, h = 12 }
          targets = [{ refId = "A", datasource = local.logs, queryType = "range", maxLines = 1000, expr = format(local.run_log_expr, s.job) }]
          options = { showTime = true, sortOrder = "Descending", wrapLogMessage = true, enableLogDetails = false, dedupStrategy = "none", showLabels = false }
      }] : p if local.status_dashboards[d].internal]) # run log is internal only: error lines can name hosts and addresses
    },
  ]]) }
}

resource "grafana_dashboard" "status" {
  for_each = local.status_dashboards
  config_json = jsonencode({
    title    = each.value.title
    uid      = each.value.uid
    refresh  = "1m"
    time     = { from = "now-24h", to = "now" }
    timezone = "browser"
    panels   = concat(local.math_panels[each.key], local.service_panels[each.key])
  })
}

resource "grafana_dashboard_public" "status" {
  for_each               = local.status_dashboards
  dashboard_uid          = grafana_dashboard.status[each.key].uid
  is_enabled             = true
  share                  = "public"
  time_selection_enabled = true # dragging across bars selects a period
  annotations_enabled    = false
}

moved {
  from = grafana_dashboard.status
  to   = grafana_dashboard.status["status"]
}

moved {
  from = grafana_dashboard_public.status
  to   = grafana_dashboard_public.status["status"]
}

output "status_page_path" {
  description = "Append to GRAFANA_URL; anyone with the link can view, so treat it as a secret"
  sensitive   = true
  value       = "/public-dashboards/${grafana_dashboard_public.status["status"].access_token}"
}

output "studio_status_page_path" {
  description = "Public link path of the Studio stack dashboard; treat it as a secret"
  sensitive   = true
  value       = "/public-dashboards/${grafana_dashboard_public.status["studio"].access_token}"
}
