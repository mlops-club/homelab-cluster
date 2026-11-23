# Purpose: Status dashboards: an internal one for everyone who runs the cluster, an external one for Studio users
# Scope: Two dashboards from one panel recipe. "Homelab status" (internal): every monitored service, with
#   per-check reports that name hosts, routes and code. "Golden Rules Studio status" (external): Golden Rules Studio
#   plus the two services it depends on, Harbor and K2, written for someone who only cares whether it is up: no
#   links to the repo, no hostnames, no infrastructure names, no run log (its error lines can carry hostnames).
#   Read-only, no variables (public dashboards don't support them)
# Overview: One block per service. Left: current state (UP / DOWN / NO DATA) and 24 h uptime. Right: one bar per
#   check run, height = how long the run took; green passed, red failed, grey = no result arrived. Under the bars,
#   one table row: readings, uptime, downtime and days measured over the last 14 days (no targets or verdicts).
#   Missing data never reads as healthy. Under that, a collapsed row explains the check, lists the exact queries
#   behind each 14-day number, and compares the selected period with the 24 h before it (status_selection.tf);
#   internally it also has the run log

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

  # ---- 14-day uptime row under each service's bars, and the queries behind it ----
  # Computed from the raw check results (probe_success) with the readings of slos.tf. Readings expected start at the
  # check's first result in the window, so a new check is measured only over the days it has existed
  window_days = trimsuffix(local.slo_window, "d")
  uptime_cols = {
    EXPECTED = "EXP"
    UP       = "UPQ"
    DOWN     = "EXP - UPQ"
    UPTIME   = "UPQ / EXP"
    DOWNTIME = "(EXP - UPQ) * (5 * 60) / LOCS" # seconds
    DAYS     = "EXP / (LOCS * 288)"            # 288 readings per day
  }
  uptime_col_order = ["EXPECTED", "UP", "DOWN", "UPTIME", "DOWNTIME", "DAYS"]
  uptime_col_names = {
    EXPECTED = "Readings expected", UP = "Readings up", DOWN = "Readings down",
    UPTIME   = "Uptime", DOWNTIME = "Downtime", DAYS = "Days measured"
  }

  uptime_expr = { for s in local.status_services : s.job => {
    for col, tmpl in local.uptime_cols : col => replace(replace(replace(tmpl,
      "EXP", "(${format(local.readings_expected_since_first, s.locs, s.job, "14 * 288")})"),
      "UPQ", "(${format(local.readings_up, s.job, local.slo_window)})"),
    "LOCS", s.locs)
  } if s.slo != null }
  u14_h     = 3  # the one-row 14-day table in the toggle
  queries_h = 13 # the pseudocode text panel in the toggle
  queries_text = { for s in local.status_services : s.job => join("\n\n", [
    "**${s.name}: the 14-day numbers above, step by step.** Every 5 minutes, each check location gives one reading: **up** if its latest result passed, **down** if it failed or if no result arrived. In pseudocode with named steps (the table runs the same PromQL with every name written out, because PromQL has no variables):",
    join("\n", [
      "```python",
      "# inputs",
      "job               = \"${s.job}\"",
      "locations         = ${s.locs}                          # probe locations running this check",
      "period            = 5 * 60                     # seconds in one reading period (5 minutes)",
      "periods_per_day   = 24 * 12                    # = 288: 12 five-minute periods an hour",
      "periods_in_window = ${local.window_days} * periods_per_day       # = 4,032: ${local.window_days} days",
      "",
      "# from the check results",
      "first_result = min(min_over_time(timestamp(probe_success{job=job})[14d:5m]))",
      "    # time of the check's first result in the window",
      "readings_up  = sum_over_time((sum(max by (probe) (avg_over_time(probe_success{job=job}[5m]))) or vector(0))[14d:5m])",
      "    # every 5 minutes, each location's share of the period its latest result passed; no result adds 0",
      "",
      "# arithmetic",
      "readings_expected = locations * clamp_max(ceil((time() - first_result) / period), periods_in_window)",
      "    # periods since the first result, at most the whole window: from the clock, not from what arrived",
      "readings_down     = readings_expected - readings_up",
      "uptime            = readings_up / readings_expected",
      "downtime          = readings_down * period / locations           # seconds",
      "days_measured     = readings_expected / (locations * periods_per_day)",
      "```",
    ]),
  ]) if s.slo != null }

  # ---- one block of rows per service ----
  dash_services = { for d, dash in local.status_dashboards : d => [for s in local.status_services : s if contains(dash.jobs, s.job)] }
  t14           = { for s in local.status_services : s.job => s.slo != null ? local.u14_h : 0 }
  tq            = { for s in local.status_services : s.job => s.slo != null ? local.queries_h : 0 }
  block_h       = { for d, services in local.dash_services : d => [for s in services : 1 + local.row_h + 1] }
  block_y       = { for d, hs in local.block_h : d => [for i, h in hs : sum(concat([0], slice(hs, 0, i)))] }
  report_h      = { for d, dash in local.status_dashboards : d => { for s in local.status_services : s.job => dash.internal ? s.report_h : 3 } }
  service_panels = { for d, services in local.dash_services : d => flatten([for i, s in services : concat([
    { id = i * 20 + 5, type = "row", title = s.name, collapsed = false, panels = [], gridPos = { x = 0, y = local.block_y[d][i], w = 24, h = 1 } },
    {
      id       = i * 20 + 1, type = "stat", title = "${s.name}: now", datasource = local.prom
      gridPos  = { x = 0, y = local.block_y[d][i] + 1, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true # always "now", whatever is selected
      targets = [{ refId = "A", instant = true,
        # latest result within the last 25 min (one 20-minute run plus slack); nothing at all means no result arrived
      expr = "min(last_over_time(probe_success{job=\"${s.job}\"}[25m])) or on() vector(-1)" }]
      options     = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { mappings = local.state_map } }
    },
    {
      id       = i * 20 + 2, type = "stat", title = "${s.name}: uptime, 24 h (no data = down)", datasource = local.prom
      gridPos  = { x = 0, y = local.block_y[d][i] + 4, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true
      targets = [{ refId = "A", instant = true,
        # same readings as the 14-day row: 5-minute readings with no result count as down; readings from before the
        # check's first result are left out, so a new check doesn't start near 0 %
      expr = "${format(local.readings_up, s.job, "24h")} / (${format(local.readings_expected_since_first, s.locs, s.job, "288")})" }]
      options = { colorMode = "value", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "percentunit", decimals = 2, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "red", value = null }, { color = "orange", value = 0.95 }, { color = "green", value = 0.99 }] } } }
    },
    {
      id       = i * 20 + 3, type = "timeseries", title = "${s.name}: time per check run", datasource = local.prom
      gridPos  = { x = 5, y = local.block_y[d][i] + 1, w = 19, h = local.row_h }
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
      id      = i * 20 + 6, type = "row", title = s.slo != null ? "${s.name}: how this check and its uptime work (click to expand)" : "${s.name}: how this check works (click to expand)", collapsed = true
      gridPos = { x = 0, y = local.block_y[d][i] + 1 + local.row_h, w = 24, h = 1 }
      panels = concat([{
        id      = i * 20 + 4, type = "text", title = "", transparent = true
        gridPos = { x = 0, y = local.block_y[d][i] + 2 + local.row_h, w = 24, h = local.report_h[d][s.job] }
        # internal: the step-by-step report (hosts, routes, code links); external: the plain-language `about`
        options = { mode = "markdown", content = local.status_dashboards[d].internal ? templatefile("${path.module}/../reports/${s.job}.md", { img = local.img_url, repo = local.repo_url }) : s.about }
        }], [for t in [{
          id      = i * 20 + 9, type = "table", datasource = local.prom
          title   = "${s.name}: last ${local.window_days} days, or since monitoring began (no result = down; the queries are below)"
          gridPos = { x = 0, y = local.block_y[d][i] + 2 + local.row_h + local.report_h[d][s.job], w = 24, h = local.u14_h }
          targets = [for col in local.uptime_col_order : { refId = col, instant = true, format = "table", expr = try(local.uptime_expr[s.job][col], "") }]
          transformations = [
            { id = "merge", options = {} },
            { id = "organize", options = {
              excludeByName = { Time = true }
              indexByName   = { for i2, c in local.uptime_col_order : "Value #${c}" => i2 }
              renameByName  = { for c in local.uptime_col_order : "Value #${c}" => local.uptime_col_names[c] }
            } },
          ]
          fieldConfig = {
            defaults = { decimals = 0 }
            overrides = [
              { matcher = { id = "byName", options = "Uptime" }, properties = [{ id = "unit", value = "percentunit" }, { id = "decimals", value = 2 }] },
              { matcher = { id = "byName", options = "Downtime" }, properties = [{ id = "unit", value = "dtdurations" }] },
              { matcher = { id = "byName", options = "Days measured" }, properties = [
              { id = "decimals", value = 1 }, { id = "unit", value = "suffix: of ${local.window_days}" }] },
            ]
          }
          }] : t if s.slo != null], [for q in [{
          id      = i * 20 + 11, type = "text", title = "", transparent = true
          gridPos = { x = 0, y = local.block_y[d][i] + 2 + local.row_h + local.report_h[d][s.job] + local.t14[s.job], w = 24, h = local.queries_h }
          options = { mode = "markdown", content = lookup(local.queries_text, s.job, "") }
        }] : q if s.slo != null], [{
        id      = i * 20 + 8, type = "table", datasource = local.prom
        title   = "Selected period vs the 24 h up to it (average seconds). Drag across the bars to pick a period (one bar = one run)"
        gridPos = { x = 0, y = local.block_y[d][i] + 2 + local.row_h + local.t14[s.job] + local.report_h[d][s.job] + local.tq[s.job], w = 24, h = 7 }
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
          id      = i * 20 + 7, type = "logs", title = "${s.name}: run log for the selected period (newest first)", datasource = local.logs
          gridPos = { x = 0, y = local.block_y[d][i] + 9 + local.row_h + local.t14[s.job] + local.report_h[d][s.job] + local.tq[s.job], w = 24, h = 12 }
          targets = [{ refId = "A", datasource = local.logs, queryType = "range", maxLines = 1000, expr = format(local.run_log_expr, s.job) }]
          options = { showTime = true, sortOrder = "Descending", wrapLogMessage = true, enableLogDetails = false, dedupStrategy = "none", showLabels = false }
      }] : p if local.status_dashboards[d].internal]) # run log is internal only: error lines can name hosts and addresses
    },
  ])]) }
}

resource "grafana_dashboard" "status" {
  for_each = local.status_dashboards
  config_json = jsonencode({
    title    = each.value.title
    uid      = each.value.uid
    refresh  = "1m"
    time     = { from = "now-24h", to = "now" }
    timezone = "browser"
    panels   = local.service_panels[each.key]
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
