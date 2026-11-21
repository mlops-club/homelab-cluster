# Purpose: "Studio OTel POC" dashboard: per page of the CTDL Golden Rules Studio, web vitals, page loads, the
#   backend calls the page makes, and recent traces; all from Tempo (TraceQL and TraceQL metrics), no metrics store
# Scope: The isolated POC instance (deployment.environment.name = otel-poc). Grafana Cloud caps TraceQL metrics at a
#   24 h range, so the dashboard opens on the last 24 h
# Overview: An overview row, then one row per page. Each page row: its screenshot (a text panel, image served from
#   this branch on raw.githubusercontent.com, like status_dashboard.tf), p75 FCP / LCP / TTFB of hard loads that
#   landed on the page (span.ce.entry_page), p75 INP / CLS while on it (span.ce.page), page views and p75 time to
#   ready (page_view spans), backend p95 latency and errors of the API calls made from the page (server spans carry
#   span.ce.page from the browser's baggage), breakdowns by user, catalog or rule, and deployment, and a table of
#   the page's recent page-view traces. Thresholds are Google's web-vitals good / needs-improvement bounds

locals {
  tempo   = { type = "tempo", uid = "grafanacloud-traces" }
  web     = "resource.service.name=\"golden-dataset-studio-web\" && resource.deployment.environment.name=\"otel-poc\""
  backend = "resource.service.name=\"golden-dataset-studio\" && resource.deployment.environment.name=\"otel-poc\""
  img_ref = "feat/studio-otel-poc"
  img_url = "https://raw.githubusercontent.com/mlops-club/homelab-cluster/${local.img_ref}/.ai/docs/adr/0001-outside-in-monitoring/images/studio-otel/pages"

  # page = ce.page value; by = the domain breakdown that makes sense on that page
  pages = [
    { id = "catalogs", title = "Catalog picker", by = "span.user.id", by_title = "user", what = "The home page: every catalog with its pages, rules approved and score." },
    { id = "rules", title = "Rules", by = "span.ce.rule.id", by_title = "rule", what = "Review a rule's values against the saved page; mark ✓ / ✕, approve a rule." },
    { id = "records", title = "Records", by = "span.ce.catalog", by_title = "catalog", what = "One course at a time: every property the rules extracted for it." },
    { id = "compare", title = "Compare", by = "span.ce.catalog", by_title = "catalog", what = "Two ruleset versions side by side: which values changed." },
    { id = "datasets", title = "Datasets", by = "span.ce.catalog", by_title = "catalog", what = "Published golden datasets: versions, files, lineage." },
    { id = "evals", title = "Evals", by = "span.ce.catalog", by_title = "catalog", what = "Extract outputs scored against the golden dataset." },
  ]

  vitals = [
    { name = "FCP", attr = "fcp.value", unit = "ms", dec = 0, good = 1800, poor = 3000, scope = "entry" },
    { name = "LCP", attr = "lcp.value", unit = "ms", dec = 0, good = 2500, poor = 4000, scope = "entry" },
    { name = "TTFB", attr = "ttfb.value", unit = "ms", dec = 0, good = 800, poor = 1800, scope = "entry" },
    { name = "INP", attr = "inp.value", unit = "ms", dec = 0, good = 200, poor = 500, scope = "page" },
    { name = "CLS", attr = "cls.value", unit = "none", dec = 3, good = 0.1, poor = 0.25, scope = "page" },
  ]

  row_h = 25 # height of one page's block: header, screenshot + stats, breakdowns, traces table

  traffic = { mode = "absolute", steps = [{ color = "green", value = null }, { color = "orange", value = 0 }] }

  page_panels = flatten([for i, p in local.pages : [
    { id = 100 * (i + 1), type = "row", title = "${p.title}  (ce.page = ${p.id})", collapsed = false, panels = [],
    gridPos = { x = 0, y = 9 + i * local.row_h, w = 24, h = 1 } },

    { id      = 100 * (i + 1) + 1, type = "text", title = "${p.title}: what it looks like",
      gridPos = { x = 0, y = 10 + i * local.row_h, w = 7, h = 11 },
    options = { mode = "markdown", content = "![${p.title} page](${local.img_url}/${p.id}.png)\n\n${p.what}" } },

    # web vitals: one stat each (instant p75 over the dashboard range)
    [for j, v in local.vitals : {
      id      = 100 * (i + 1) + 10 + j, type = "stat", title = "p75 ${v.name}", datasource = local.tempo
      gridPos = { x = 7 + (j % 3) * 3, y = 10 + i * local.row_h + floor(j / 3) * 4, w = 3, h = j < 3 ? 4 : 7 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.web} && name=\"${v.name}\" && span.ce.${v.scope == "entry" ? "entry_page" : "page"}=\"${p.id}\"} | quantile_over_time(span.${v.attr}, .75)" }]
      options = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = v.unit, decimals = v.dec, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "green", value = null }, { color = "orange", value = v.good }, { color = "red", value = v.poor }] } } }
    }],
    {
      id      = 100 * (i + 1) + 20, type = "stat", title = "Page views", datasource = local.tempo
      gridPos = { x = 13, y = 14 + i * local.row_h, w = 3, h = 7 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.web} && name=\"page_view\" && span.ce.page=\"${p.id}\"} | count_over_time()" }]
      options     = { colorMode = "none", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "short", decimals = 0, noValue = "0" } }
    },
    {
      id          = 100 * (i + 1) + 21, type = "stat", title = "p75 time to ready", datasource = local.tempo,
      description = "page_view span: route change (or navigation start) until the page's API calls finished"
      gridPos     = { x = 16, y = 10 + i * local.row_h, w = 4, h = 4 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.web} && name=\"page_view\" && span.ce.page=\"${p.id}\"} | quantile_over_time(span.ce.page.ready.duration_ms, .75)" }]
      options = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "ms", decimals = 0, noValue = "no data", thresholds = { mode = "absolute",
      steps = [{ color = "green", value = null }, { color = "orange", value = 1000 }, { color = "red", value = 3000 }] } } }
    },
    {
      id          = 100 * (i + 1) + 22, type = "stat", title = "Backend errors", datasource = local.tempo,
      description = "Server spans of calls made from this page with status error or HTTP >= 400"
      gridPos     = { x = 20, y = 10 + i * local.row_h, w = 4, h = 4 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.backend} && kind=server && span.ce.page=\"${p.id}\" && (status=error || span.http.response.status_code >= 400)} | count_over_time()" }]
      options = { colorMode = "background", graphMode = "none", textMode = "value", reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "short", decimals = 0, noValue = "0", thresholds = { mode = "absolute",
      steps = [{ color = "green", value = null }, { color = "red", value = 1 }] } } }
    },
    {
      id      = 100 * (i + 1) + 23, type = "bargauge", title = "p95 backend latency by API route (calls from this page)", datasource = local.tempo
      gridPos = { x = 16, y = 14 + i * local.row_h, w = 8, h = 7 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.backend} && kind=server && span.ce.page=\"${p.id}\"} | quantile_over_time(duration, .95) by (span.http.route)" }]
      options     = { orientation = "horizontal", displayMode = "basic", showUnfilled = true, reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "s", decimals = 3, displayName = "$${__field.labels[\"span.http.route\"]}" } }
    },
    # breakdowns: user, catalog or rule, deployment (commit / image tag)
    [for k, b in [
      { t = "p75 time to ready by user", by = "span.user.id" },
      { t = "p75 time to ready by ${p.by_title}", by = p.by },
      { t = "p75 time to ready by deployment (image tag)", by = "resource.deployment.name" },
      ] : {
      id      = 100 * (i + 1) + 30 + k, type = "bargauge", title = b.t, datasource = local.tempo
      gridPos = { x = k * 8, y = 21 + i * local.row_h, w = 8, h = 5 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "instant",
      query = "{${local.web} && name=\"page_view\" && span.ce.page=\"${p.id}\"} | quantile_over_time(span.ce.page.ready.duration_ms, .75) by (${b.by})" }]
      options     = { orientation = "horizontal", displayMode = "basic", showUnfilled = true, reduceOptions = { calcs = ["lastNotNull"] } }
      fieldConfig = { defaults = { unit = "ms", decimals = 0, displayName = "$${__field.labels[\"${b.by}\"]}" } }
    }],
    {
      id      = 100 * (i + 1) + 40, type = "table", title = "Recent ${p.title} page views (click a trace ID for the browser → server trace)", datasource = local.tempo
      gridPos = { x = 0, y = 26 + i * local.row_h, w = 24, h = 8 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", tableType = "traces", limit = 20,
      query = "{${local.web} && name=\"page_view\" && span.ce.page=\"${p.id}\"} | select(span.user.id, span.ce.catalog, span.ce.page.ready.duration_ms, span.ce.stats.api.calls, resource.deployment.name)" }]
    },
  ]])

  overview = [
    { id = 1, type = "text", title = "", transparent = true, gridPos = { x = 0, y = 0, w = 24, h = 2 },
    options = { mode = "markdown", content = "**CTDL Golden Rules Studio, OpenTelemetry POC** (isolated instance, `deployment.environment.name = otel-poc`). All panels are TraceQL / TraceQL metrics on Tempo: no metrics store. Web vitals of hard loads are grouped by the page the browser landed on (`span.ce.entry_page`); INP and CLS by the page shown when reported (`span.ce.page`). Grafana Cloud limits TraceQL metrics to 24 h." } },
    {
      id      = 2, type = "timeseries", title = "Page views by page", datasource = local.tempo
      gridPos = { x = 0, y = 2, w = 12, h = 7 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "range",
      query = "{${local.web} && name=\"page_view\"} | count_over_time() by (span.ce.page)" }]
      fieldConfig = { defaults = { unit = "short", displayName = "$${__field.labels[\"span.ce.page\"]}", custom = { drawStyle = "bars", fillOpacity = 70, stacking = { mode = "normal" } } } }
    },
    {
      id      = 3, type = "timeseries", title = "Backend p95 latency by route", datasource = local.tempo
      gridPos = { x = 12, y = 2, w = 12, h = 7 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", metricsQueryType = "range",
      query = "{${local.backend} && kind=server} | quantile_over_time(duration, .95) by (span.http.route)" }]
      fieldConfig = { defaults = { unit = "s", displayName = "$${__field.labels[\"span.http.route\"]}" } }
    },
  ]
}

resource "grafana_folder" "studio_otel" {
  title = "Studio OTel POC"
  uid   = "studio-otel-poc"
}

resource "grafana_dashboard" "studio_otel" {
  folder = grafana_folder.studio_otel.uid
  config_json = jsonencode({
    title    = "Studio OTel POC: pages"
    uid      = "studio-otel-pages"
    time     = { from = "now-24h", to = "now" }
    timezone = "browser"
    refresh  = ""
    tags     = ["studio", "otel", "poc"]
    panels   = concat(local.overview, local.page_panels)
  })
}

output "dashboard_url" {
  value = grafana_dashboard.studio_otel.url
}

# One trace, by ID (?var-trace=<trace id>): the browser → server waterfall, for reports and links from alerts
resource "grafana_dashboard" "studio_otel_trace" {
  folder = grafana_folder.studio_otel.uid
  config_json = jsonencode({
    title      = "Studio OTel POC: one trace"
    uid        = "studio-otel-trace"
    time       = { from = "now-24h", to = "now" }
    timezone   = "browser"
    templating = { list = [{ name = "trace", type = "textbox", label = "Trace ID", query = "" }] }
    panels = [{
      id      = 1, type = "traces", title = "Trace $${trace}", datasource = local.tempo
      gridPos = { x = 0, y = 0, w = 24, h = 20 }
      targets = [{ refId = "A", datasource = local.tempo, queryType = "traceql", query = "$${trace}" }]
    }]
  })
}
