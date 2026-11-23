# Purpose: Status dashboards shared by public link, standing in for a status page
# Scope: Grafana POC test 7. Two dashboards built from one panel recipe: "Homelab status" (every listener-facing
#   service) and "Studio stack status" (Golden Rules Studio plus the two services it depends on, Harbor and K2).
#   Read-only, no variables (public dashboards don't support them)
# Overview: A collapsed "How the SLOs are calculated" row at the top walks through the SLO math with rendered
#   formulas, then substitutes each service's live numbers. Below it, one row per service. Left: current state
#   (UP / DOWN / NO DATA) and 24 h uptime. Right: one bar per check run, height = how long the run took; green
#   passed, red failed, grey = no result arrived (probe, network or Grafana problem). Missing data never reads as
#   healthy. Under each service, a collapsed row holds a step-by-step report (monitoring/reports/<job>.md), then two
#   panels that follow the dashboard time range (the "selection"): a comparison of the selected period against the
#   24 h before it, and the run log. Signed in, click a bar to select that run; anywhere, drag across the bars to
#   select a period. The bars zoom to the selection; the stats stay on the last 24 h (status_selection.tf)

locals {
  # locs: probe locations running the check; report_h: height of the report text panel;
  # slo: key in local.slo_services (slos.tf), or null
  status_services = [
    { name = "Jellyfin", job = "jellyfin-login", every = "15m", locs = 1, report_h = 21, slo = "jellyfin" },
    { name = "Navidrome", job = "navidrome-login", every = "15m", locs = 1, report_h = 21, slo = "navidrome" },
    { name = "Photos (Immich)", job = "immich-login", every = "15m", locs = 1, report_h = 21, slo = "immich" },
    { name = "Audiobookshelf", job = "audiobookshelf-login", every = "15m", locs = 2, report_h = 21, slo = "audiobookshelf" },
    { name = "Audiobookshelf page load (Oregon, Ohio)", job = "audiobookshelf-browser", every = "15m", locs = 2, report_h = 21, slo = null },
    { name = "Golden Rules Studio", job = "golden-rules-studio-health", every = "15m", locs = 2, report_h = 9, slo = "golden-rules-studio" },
    { name = "Harbor (container registry)", job = "harbor-health", every = "5m", locs = 1, report_h = 9, slo = "harbor" },
    { name = "K2", job = "k2-health", every = "5m", locs = 1, report_h = 9, slo = "k2" },
  ]
  status_dashboards = {
    status = { title = "Homelab status", uid = "homelab-status", jobs = [for s in local.status_services : s.job] }
    studio = {
      title = "Studio stack status", uid = "studio-stack-status"
      jobs  = ["golden-rules-studio-health", "harbor-health", "k2-health"]
    }
  }

  prom  = { type = "prometheus", uid = "grafanacloud-prom" }
  row_h = 6
  # Screenshots and links point at the public repo; switch docs_ref to "main" once the PR merges
  docs_ref = "docs/adr-outside-in-monitoring"
  repo_url = "https://github.com/mlops-club/homelab-cluster/blob/${local.docs_ref}"
  raw_url  = "https://raw.githubusercontent.com/mlops-club/homelab-cluster/${local.docs_ref}/.ai/docs/adr/0001-outside-in-monitoring/images"
  img_url  = "${local.raw_url}/grafana-poc/steps"
  math_url = "${local.raw_url}/slo-math"
  state_map = [{ type = "value", options = {
    "-1" = { text = "NO DATA", color = "#6e6e6e", index = 0 }
    "0"  = { text = "DOWN", color = "red", index = 1 }
    "1"  = { text = "UP", color = "green", index = 2 }
  } }]

  # ---- SLO math row (top of each dashboard) ----
  math_row_h = 1
  math_text = join("\n", [
    "Each SLO asks: **of the results the schedule promised, what share passed?** A result that never arrived (probe, network or Grafana down) counts as failed, so silence can't look healthy. The cards name every term first, then the table under them substitutes each service's live numbers. Target T = ${local.slo_objective * 100} %, window W = ${local.slo_window} (or since the SLO was created, if newer).",
    "",
    "**How Grafana counts it:** time is cut into 5-minute slots, one per probe location. A slot is good when the check's latest result in it passed, bad when it failed, and also bad when nothing arrived. So E = expected slots and G = passing slots; a failed 15-minute run counts for the ~15 minutes its result stands.",
    "",
    "<img src=\"${local.math_url}/slo-legend.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-step1-expected.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-step2-sli.png\" width=\"32%\">",
    "<img src=\"${local.math_url}/slo-step3-budget.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-step4-spent.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-step5-verdict.png\" width=\"32%\">",
    "<img src=\"${local.math_url}/slo-example.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-received-vs-expected.png\" width=\"32%\"> <img src=\"${local.math_url}/slo-burn-rate.png\" width=\"32%\">",
  ])
  # One query per table column, one series per service (label `service`), from Grafana SLO's own 5-minute
  # recording rules: success = passed runs per bucket, total = expected runs per bucket (slos.tf)
  slo_window_sub = "[${local.slo_window}:5m]"
  slo_col = {
    E = "sum_over_time((grafana_slo_total_rate_5m{grafana_slo_uuid=\"UUID\"} < +Inf)${local.slo_window_sub})"
    G = "sum_over_time((grafana_slo_success_rate_5m{grafana_slo_uuid=\"UUID\"} < +Inf)${local.slo_window_sub})"
  }
  slo_math_targets = { for d, dash in local.status_dashboards : d => {
    for col, tmpl in {
      E     = "(${local.slo_col.E})"
      G     = "(${local.slo_col.G})"
      F     = "(${local.slo_col.E} - ${local.slo_col.G})"
      SLI   = "(${local.slo_col.G} / ${local.slo_col.E})"
      B     = "((1 - ${local.slo_objective}) * ${local.slo_col.E})"
      SPENT = "((${local.slo_col.E} - ${local.slo_col.G}) / ((1 - ${local.slo_objective}) * ${local.slo_col.E}))"
      OK    = "(${local.slo_col.G} / ${local.slo_col.E} >= bool ${local.slo_objective})"
      } : col => join(" or ", [for s in local.status_services :
        "label_replace(sum(${replace(tmpl, "UUID", grafana_slo.availability[s.slo].id)}), \"service\", \"${s.name}\", \"\", \"\")"
    if s.slo != null && contains(dash.jobs, s.job)])
  } }
  math_panels = { for d, dash in local.status_dashboards : d => [
    {
      id = 901, type = "row", title = "How the SLOs are calculated (click to expand)", collapsed = true
      gridPos = { x = 0, y = 0, w = 24, h = 1 }
      panels = [
        {
          id = 902, type = "text", title = "", transparent = true
          gridPos = { x = 0, y = 1, w = 24, h = 34 }
          options = { mode = "markdown", content = local.math_text }
        },
        {
          id = 903, type = "table", datasource = local.prom
          title   = "Live numbers: each service's terms substituted into the formulas. E and G count 5-minute slots per probe location; verdict = SLI ≥ ${local.slo_objective * 100} % (window ${local.slo_window})"
          gridPos = { x = 0, y = 35, w = 24, h = 9 }
          targets = [for col in ["E", "G", "F", "SLI", "B", "SPENT", "OK"] :
          { refId = col, instant = true, format = "table", expr = local.slo_math_targets[d][col] }]
          transformations = [
            { id = "merge", options = {} },
            { id = "organize", options = {
              excludeByName = { Time = true }
              indexByName   = { service = 0, "Value #E" = 1, "Value #G" = 2, "Value #F" = 3, "Value #SLI" = 4, "Value #B" = 5, "Value #SPENT" = 6, "Value #OK" = 7 }
              renameByName = {
                service = "Service", "Value #E" = "E (expected slots)", "Value #G" = "G (passing slots)",
                "Value #F" = "F = E − G", "Value #SLI" = "SLI = G ÷ E", "Value #B" = "B = (1 − T) × E",
                "Value #SPENT" = "Spent = F ÷ B", "Value #OK" = "Verdict"
              }
            } },
          ]
          fieldConfig = {
            defaults = { decimals = 1 }
            overrides = [
              { matcher = { id = "byName", options = "SLI = G ÷ E" }, properties = [
                { id = "unit", value = "percentunit" }, { id = "decimals", value = 3 },
                { id = "custom.cellOptions", value = { type = "color-text" } },
                { id = "thresholds", value = { mode = "absolute", steps = [{ color = "red", value = null }, { color = "green", value = local.slo_objective }] } },
              ] },
              { matcher = { id = "byName", options = "B = (1 − T) × E" }, properties = [{ id = "decimals", value = 2 }] },
              { matcher = { id = "byName", options = "Spent = F ÷ B" }, properties = [
                { id = "unit", value = "percentunit" }, { id = "decimals", value = 0 },
                { id = "custom.cellOptions", value = { type = "color-text" } },
                { id = "thresholds", value = { mode = "absolute", steps = [{ color = "green", value = null }, { color = "orange", value = 0.5 }, { color = "red", value = 1 }] } },
              ] },
              { matcher = { id = "byName", options = "Verdict" }, properties = [
                { id = "custom.cellOptions", value = { type = "color-background" } },
                { id = "mappings", value = [{ type = "value", options = {
                  "1" = { text = "SLO met", color = "green", index = 0 }
                  "0" = { text = "SLO violated", color = "red", index = 1 }
                } }] },
              ] },
            ]
          }
        },
      ]
    },
  ] }

  # ---- one block of rows per service ----
  dash_services = { for d, dash in local.status_dashboards : d => [for s in local.status_services : s if contains(dash.jobs, s.job)] }
  service_panels = { for d, services in local.dash_services : d => flatten([for i, s in services : [
    { id = i * 10 + 5, type = "row", title = s.name, collapsed = false, panels = [], gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2), w = 24, h = 1 } },
    {
      id       = i * 10 + 1, type = "stat", title = "${s.name}: now", datasource = local.prom
      gridPos  = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 1, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true # always "now", whatever is selected
      targets = [{ refId = "A", instant = true,
        # last result within ~1.3 check intervals; nothing at all means the probe or network is down
      expr = "min(last_over_time(probe_success{job=\"${s.job}\"}[20m])) or on() vector(-1)" }]
      options     = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { mappings = local.state_map } }
    },
    {
      id       = i * 10 + 2, type = "stat", title = "${s.name}: uptime, 24 h (no data = down)", datasource = local.prom
      gridPos  = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 4, w = 5, h = 3 }
      timeFrom = "24h", hideTimeOverride = true
      targets = [{ refId = "A", instant = true,
        # same slot math as the SLOs (slos.tf): 5-minute slots with no result count as down; slots from before
        # the check's first-ever result are left out, so a new check doesn't start near 0 %
      expr = "${format(local.slot_good, s.job, "24h")} / sum_over_time((vector(${s.locs}) and on() (count(count_over_time(probe_success{job=\"${s.job}\"}[30d])) > 0))[24h:5m])" }]
      options = { colorMode = "value", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "percentunit", decimals = 2, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "red", value = null }, { color = "orange", value = 0.99 }, { color = "green", value = 0.999 }] } } }
    },
    {
      id       = i * 10 + 3, type = "timeseries", title = "${s.name}: time per check run", datasource = local.prom
      gridPos  = { x = 5, y = local.math_row_h + i * (local.row_h + 2) + 1, w = 19, h = local.row_h }
      interval = s.every # one bar per check run
      targets = [
        { refId = "A", legendFormat = "Passed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 1)" },
        { refId = "B", legendFormat = "Failed",
        expr = "max(last_over_time(probe_duration_seconds{job=\"${s.job}\"}[$__interval])) and on() (min(last_over_time(probe_success{job=\"${s.job}\"}[$__interval])) == 0)" },
        { refId = "C", legendFormat = "No result",
        expr = "(vector(0.5) unless on() count(count_over_time(probe_success{job=\"${s.job}\"}[20m]))) and on() (count(count_over_time(probe_success{job=\"${s.job}\"}[30d])) > 0)" },
      ]
      options = { legend = { showLegend = true, displayMode = "list", placement = "bottom" }, tooltip = { mode = "single" } }
      fieldConfig = {
        defaults = { unit = "s", min = 0,
          # Click a bar: select that run (the 30 min around the bar always hold it); the toggle below shows its log.
          # Signed-in dashboard only: public dashboards hide data links (drag across a bar there instead).
          # One-click: clicking a bar follows this link directly, no menu
          links = [
            { title = "Select this run (log in the toggle below)", url = "/d/${local.status_dashboards[d].uid}/x?time=$${__value.time}&time.window=1800000", oneClick = true },
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
      panels = [{
        id      = i * 10 + 4, type = "text", title = "", transparent = true
        gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 2 + local.row_h, w = 24, h = s.report_h }
        options = { mode = "markdown", content = templatefile("${path.module}/../reports/${s.job}.md", { img = local.img_url, repo = local.repo_url }) }
        }, {
        id      = i * 10 + 8, type = "table", datasource = local.prom
        title   = "Selected period vs the 24 h up to it (average seconds). Drag across the bars to pick a period (one bar = one run)"
        gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 2 + s.report_h + local.row_h, w = 24, h = 7 }
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
        }, {
        id      = i * 10 + 7, type = "logs", title = "${s.name}: run log for the selected period (newest first)", datasource = local.logs
        gridPos = { x = 0, y = local.math_row_h + i * (local.row_h + 2) + 9 + s.report_h + local.row_h, w = 24, h = 12 }
        targets = [{ refId = "A", datasource = local.logs, queryType = "range", maxLines = 1000, expr = format(local.run_log_expr, s.job) }]
        options = { showTime = true, sortOrder = "Descending", wrapLogMessage = true, enableLogDetails = false, dedupStrategy = "none", showLabels = false }
      }]
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
