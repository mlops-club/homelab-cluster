#!/usr/bin/env python3
"""Write bubbleup.json: the "Studio OTel POC: compare a selection" dashboard (a BubbleUp-style view over Tempo).

Usage: python3 bubbleup.py > bubbleup.json   (bubbleup.tf loads the JSON; re-run after editing this file)

Pick which spans to look at, which numeric attribute is the y-axis (x is time), and a band on that axis. The heatmap
shows every span; the table runs TraceQL compare() and lists, for each attribute value, how many of its spans fall
inside the band against how many fall outside, sorted by the share inside. Values far above the overall share are what
makes the selection different. Grafana's Traces Drilldown app does the same with a box drawn on the heatmap, but
only with duration on the y-axis.
"""

import json

TEMPO = {"type": "tempo", "uid": "grafanacloud-traces"}
EXPR = {"type": "__expr__", "uid": "__expr__"}
ENV = 'resource.deployment.environment.name="otel-poc"'

# label : TraceQL conditions (no commas: Grafana custom variables split on them)
SPANS = [
    ("Backend requests", 'resource.service.name="golden-dataset-studio" && kind=server'),
    ("Page views (browser)", 'resource.service.name="golden-dataset-studio-web" && name="page_view"'),
    ("API calls (browser)", 'resource.service.name="golden-dataset-studio-web" && kind=client'),
    ("LCP reports (browser)", 'resource.service.name="golden-dataset-studio-web" && name="LCP"'),
]
# label : numeric attribute. TraceQL metrics skip float attributes, so only integers (and duration) are listed
Y = [
    ("Duration", "duration"),
    ("Page: time to ready (ms)", "span.ce.page.ready.duration_ms"),
    ("Page: slowest API call (ms)", "span.ce.stats.api.slowest_ms"),
    ("Page: DOM nodes", "span.ce.page.dom_nodes"),
    ("LCP (ms)", "span.lcp.value"),
    ("Response size (bytes)", "span.http.response.body.size"),
    ("Snapshot rows", "span.ce.snapshot.rows"),
    ("Rows total", "span.ce.rows.total"),
]
# attributes that are unique per span or per page load: they never explain a selection
NOISE = r"([^=]+=[-0-9.e+]+|.*sha256.*|.*(navigation_id|navigation_start_time|client\.port|page_view\.id|session\.id|\.delta|_time\b|_time=|deployment\.id|pipeline\.run\.id|SampleRate|instrumentation:|ce\.page\.stem).*)"

MIN_IN_BAND = 3
# attributes worth grouping by (low cardinality); the Group by box also takes any attribute typed in
GROUP_BY = [(a, a) for a in ("span.ce.page", "span.ce.catalog", "span.http.route", "name", "span.user.id",
                              "span.ce.request.type", "span.http.response.status_code", "span.ce.rule.id",
                              "span.ce.page_view.kind", "resource.browser.name", "status")]  # a value seen on one or two spans in the band says little


# the string attributes shown in a dot's tooltip, plus the y-axis attribute (duration is always on a span row)
SELECT = "${y}, span.ce.page, span.ce.catalog, span.user.id, span.http.route, span.ce.course.key"
EXPLORE = ('{"datasource":"grafanacloud-traces","queries":[{"refId":"A","queryType":"traceql",'
           '"query":"${__data.fields.traceIdHidden}"}],"range":{"from":"${__from}","to":"${__to}"}}')


def search(ref, traceql):
    return {"refId": ref, "datasource": TEMPO, "queryType": "traceql", "tableType": "spans",
            "limit": 1000, "spss": 100, "query": traceql}


def custom(name, label, options, current):
    query = ",".join(f"{k} : {v}" for k, v in options)
    opts = [{"text": k, "value": v, "selected": v == current} for k, v in options]
    cur = next(o for o in opts if o["selected"])
    return {"name": name, "label": label, "type": "custom", "query": query, "options": opts,
            "current": {"text": cur["text"], "value": cur["value"]}}


def textbox(name, label, value, desc):
    return {"name": name, "label": label, "type": "textbox", "query": value, "description": desc,
            "current": {"text": value, "value": value}}


# Honeycomb-style WHERE: Grafana ad hoc filter bars. Their keys and values autocomplete from Tempo (values only those
# seen with the other filters), but a bar renders as `a="x",b="y"`, which is not TraceQL. A pipeline of spanset filters
# is: each bar gets its own stage, `| {a="x"}`, and an empty bar is `| {}` (every span). So: one condition per bar.
FILTERS = ("where", "and")
cond = f"${{spans}} && {ENV}"
stages = "".join(f" | {{${{{f}}}}}" for f in FILTERS)
base = f"{{{cond}}}{stages}"
band = "${y} >= ${lo} && ${y} <= ${hi}"
q = lambda traceql, kind="range": {"refId": "A", "datasource": TEMPO, "queryType": "traceql",
                                   "metricsQueryType": kind, "query": traceql}

intro = """**Compare a selection** (BubbleUp-style). Choose **Spans**, the **Y-axis** attribute and a band on it (**From** /
**To**; duration takes units such as `500ms` or `2s`, other attributes plain numbers). Narrow the spans with the **Where**
and **And** filter bars (names and values autocomplete from Tempo; one condition per bar) and split counts with **Group by**.
The heatmap shows the shape, the dot chart every span (click one for its trace). At the bottom, one histogram per attribute:
for each value, the share of the spans **in the band** (orange) next to the share of **everything else** (gray). A value
whose orange bar is much longer than its gray one is what the selection has in common. Drag on the heatmap to narrow the
time range. Traces Drilldown has the same view for a box drawn on a duration heatmap:
[Traces Drilldown](/a/grafana-exploretraces-app/explore) → Duration → select a region → Comparison."""

panels = [
    {"id": 1, "type": "text", "title": "", "gridPos": {"x": 0, "y": 0, "w": 24, "h": 5},
     "options": {"mode": "markdown", "content": intro}},
    {"id": 2, "type": "heatmap", "title": "${y} over time: all ${spans:text}", "datasource": TEMPO,
     "description": "TraceQL histogram_over_time: buckets are powers of two. The band you selected is From..To",
     "gridPos": {"x": 0, "y": 5, "w": 18, "h": 10},
     "targets": [q(f"{base} | histogram_over_time(${{y}})")],
     "fieldConfig": {"defaults": {"unit": "short"}},
     "options": {"calculate": False, "yAxis": {"axisPlacement": "left", "unit": "short"}, "cellGap": 1,
                 "color": {"mode": "scheme", "scheme": "Blues", "scale": "exponential", "exponent": 0.5, "fill": "dark-blue"},
                 "rowsFrame": {"layout": "auto"}, "tooltip": {"mode": "single", "yHistogram": True},
                 "legend": {"show": True}, "exemplars": {"color": "orange"}}},
    {"id": 3, "type": "stat", "title": "In the band", "datasource": TEMPO,
     "gridPos": {"x": 18, "y": 5, "w": 3, "h": 4},
     "targets": [q(f"{{{cond} && {band}}}{stages} | count_over_time()", "instant")],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "noValue": "0"}}},
    {"id": 4, "type": "stat", "title": "All spans", "datasource": TEMPO,
     "gridPos": {"x": 21, "y": 5, "w": 3, "h": 4},
     "targets": [q(f"{base} | count_over_time()", "instant")],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "noValue": "0"}}},
    {"id": 5, "type": "stat", "title": "Overall share in the band", "datasource": TEMPO,
     "description": "In the band / all spans. A value whose share in the table is well above this is overrepresented",
     "gridPos": {"x": 18, "y": 9, "w": 6, "h": 6},
     "targets": [dict(q(f"{{{cond} && {band}}}{stages} | count_over_time()", "instant"), refId="A", hide=True),
                 dict(q(f"{base} | count_over_time()", "instant"), refId="B", hide=True),
                 # instant TraceQL results carry different timestamps, so reduce each to a number before dividing
                 {"refId": "RA", "datasource": EXPR, "type": "reduce", "expression": "A", "reducer": "last", "hide": True},
                 {"refId": "RB", "datasource": EXPR, "type": "reduce", "expression": "B", "reducer": "last", "hide": True},
                 {"refId": "C", "datasource": EXPR, "type": "math", "expression": "$RA / $RB"}],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "percentunit", "decimals": 1, "noValue": "–"}}},
    {"id": 8, "type": "timeseries", "title": "How many: ${spans:text} by ${by}", "datasource": TEMPO,
     "description": "TraceQL count_over_time() by the Group by attribute (spans without it are one series)",
     "gridPos": {"x": 0, "y": 15, "w": 12, "h": 9},
     "targets": [q(f"{base} | count_over_time() by (${{by}})")],
     "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "bars", "fillOpacity": 70, "stacking": {"mode": "normal"},
                                                          "lineWidth": 0}}},
     "options": {"legend": {"showLegend": True, "displayMode": "table", "placement": "right", "calcs": ["sum"],
                            "sortBy": "Total", "sortDesc": True}, "tooltip": {"mode": "multi", "sort": "desc"}}},
    {"id": 9, "type": "timeseries", "title": "p90 ${y:text} by ${by}", "datasource": TEMPO,
     "description": "TraceQL quantile_over_time(y, 0.9) by the Group by attribute, log scale. Duration is in seconds",
     "gridPos": {"x": 12, "y": 15, "w": 12, "h": 9},
     "targets": [q(f"{base} | quantile_over_time(${{y}}, .9) by (${{by}})")],
     "transformations": [{"id": "renameByRegex", "options": {"regex": r'\{p=0\.9, [^=]+="(.*)"\}', "renamePattern": "$1"}},
                         {"id": "renameByRegex", "options": {"regex": r"^0\.9$", "renamePattern": "(not set)"}}],
     "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "points", "pointSize": 7, "showPoints": "always",
                                                          # log scale: Tempo reports empty intervals as 0, which drop out
                                                          "scaleDistribution": {"type": "log", "log": 2}}}},
     "options": {"legend": {"showLegend": True, "displayMode": "table", "placement": "right", "calcs": ["max"],
                            "sortBy": "Max", "sortDesc": True}, "tooltip": {"mode": "multi", "sort": "desc"}}},
    {"id": 7, "type": "xychart", "title": "Every span: ${y:text} over time. Click a dot, then a link, for its trace",
     "datasource": TEMPO,
     "description": "TraceQL search, one dot per span (up to 1000 traces, 100 spans each: on a busy range not every span "
                    "is shown, so narrow the time range). Duration is shown in time units. The Tempo panel merges every "
                    "query into one frame, so spans in the band cannot be coloured separately: use the counts and the "
                    "table below for the band",
     "gridPos": {"x": 0, "y": 24, "w": 24, "h": 14},
     "targets": [search("A", f"{base} | select({SELECT})")],
     # selected attributes arrive as text: make the y-axis candidates numbers. A span row always ends with duration,
     # so the first number on a row is the y-axis attribute when one is selected, and duration otherwise
     "transformations": [{"id": "convertFieldType", "options": {"conversions": [
         {"targetField": v.removeprefix("span."), "destinationType": "number"} for _, v in Y if v != "duration"]}}],
     "fieldConfig": {
         "defaults": {"unit": "short", "custom": {"show": "points", "pointSize": {"fixed": 6}, "pointShape": "circle",
                                                  "fillOpacity": 60},
                      "color": {"mode": "fixed", "fixedColor": "orange"},
                      "links": [{"title": "Open this trace", "url": "/d/studio-otel-trace?var-trace=${__data.fields.traceIdHidden}&${__url_time_range}"},
                                {"title": "Open in Explore", "url": "/explore?left=" + EXPLORE}]},
         "overrides": [{"matcher": {"id": "byName", "options": "duration"}, "properties": [{"id": "unit", "value": "ns"}]}]},
     "options": {"mapping": "manual",
                 "series": [{"frame": {"matcher": {"id": "byIndex", "options": 0}}, "name": {"fixed": "spans"},
                             "x": {"matcher": {"id": "byName", "options": "time"}},
                             "y": {"matcher": {"id": "byType", "options": "number"}}}],
                 "tooltip": {"mode": "single"}, "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"}}},
]

# -- BubbleUp: one histogram per attribute, a pair of bars per value ------------------------------------------------
# For each attribute: the share of the band's spans with each value next to the share of all other spans with it.
# Shares come from server-side expressions: count by value (reduced to numbers) divided by the group's total. Strings
# group by value (top 10 by share in the band); numbers group into TraceQL's power-of-two buckets.
outside = "(${y} < ${lo} || ${y} > ${hi})"
IN_COLOR, OUT_COLOR = "orange", "#94a3b8"
# (attribute, kind, title): kind "str" = count by value, "num" = histogram buckets
BACKEND_ATTRS = [("span.http.route", "str", "Route"), ("span.ce.page", "str", "Page (from the browser)"),
                 ("span.ce.catalog", "str", "Catalog"), ("span.ce.course.key", "str", "Course"),
                 ("span.ce.rule.id", "str", "Rule"), ("span.ce.snapshot.cache", "str", "Snapshot cache"),
                 ("span.http.response.status_code", "str", "Status code"), ("span.user.id", "str", "User"),
                 ("span.http.response.body.size", "num", "Response size (bytes)")]
BROWSER_ATTRS = [("span.ce.page", "str", "Page"), ("span.ce.catalog", "str", "Catalog"),
                 ("span.ce.page_view.kind", "str", "Hard or soft load"), ("span.url.template", "str", "API call"),
                 ("span.user.id", "str", "User"), ("resource.browser.name", "str", "Browser"),
                 ("span.ce.stats.api.calls", "num", "API calls per page"), ("span.ce.page.dom_nodes", "num", "DOM nodes")]
_ids = iter(range(100, 200))


def share_targets(metric, label):
    """IN and OUT: for each value of `label`, its share of the band's spans and of the other spans."""
    t = []
    for g, sel in (("I", band), ("O", outside)):
        t += [dict(q(f"{{{cond} && {sel}}}{stages} | {metric}", "instant"), refId=f"{g}V", hide=True),
              # grouped by service too, so the total's labels are a subset of each value's (else the division can't pair them)
              dict(q(f"{{{cond} && {sel}}}{stages} | count_over_time() by (resource.service.name)", "instant"),
                   refId=f"{g}T", hide=True),
              {"refId": f"{g}RV", "datasource": EXPR, "type": "reduce", "expression": f"{g}V", "reducer": "last", "hide": True},
              {"refId": f"{g}RT", "datasource": EXPR, "type": "reduce", "expression": f"{g}T", "reducer": "last", "hide": True},
              {"refId": "IN" if g == "I" else "OUT", "datasource": EXPR, "type": "math", "expression": f"${g}RV / ${g}RT"}]
    return t


def attr_panel(attr, kind, title, x, y, w=12, h=9):
    label = "__bucket" if kind == "num" else attr
    metric = (f"histogram_over_time({attr}) by (resource.service.name)" if kind == "num"
              else f"count_over_time() by ({attr}, resource.service.name)")
    tr = [{"id": "reduce", "options": {"mode": "seriesToRows", "reducers": ["lastNotNull"], "labelsToFields": True}},
          {"id": "groupingToMatrix", "options": {"columnField": "Field", "rowField": label, "valueField": "Last *",
                                                 "emptyValue": "zero"}},
          {"id": "organize", "options": {"renameByName": {f"{label}\\Field": "value", "IN": "in the band",
                                                          "OUT": "everything else"}}}]
    if kind == "num":
        tr += [{"id": "convertFieldType", "options": {"conversions": [{"targetField": "value", "destinationType": "number"}]}},
               {"id": "sortBy", "options": {"sort": [{"field": "value"}]}},
               {"id": "convertFieldType", "options": {"conversions": [{"targetField": "value", "destinationType": "string"}]}}]
    else:
        tr += [{"id": "sortBy", "options": {"sort": [{"field": "in the band", "desc": True}, {"field": "everything else", "desc": True}]}},
               {"id": "limit", "options": {"limitField": 10}}]
    return {"id": next(_ids), "type": "barchart", "title": title, "datasource": TEMPO,
            "description": f"{attr}: share of the spans in the band (orange) and of all other spans (gray) with each "
                           + ("value (top 10)" if kind == "str" else "value, in power-of-two buckets (upper bounds)"),
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": share_targets(metric, label),
            "transformations": tr,
            "fieldConfig": {"defaults": {"unit": "percentunit", "decimals": 0, "min": 0, "max": 1,
                                         "custom": {"fillOpacity": 85, "lineWidth": 0}},
                            "overrides": [
                                # label values arrive quoted ("marshall"); nil = spans without the attribute
                                {"matcher": {"id": "byName", "options": "value"}, "properties": [{"id": "mappings", "value": [
                                    {"type": "regex", "options": {"pattern": '^"(.*)"$', "result": {"text": "$1"}}},
                                    {"type": "value", "options": {"nil": {"text": "(not set)"}}},
                                    {"type": "special", "options": {"match": "empty", "result": {"text": "(not set)"}}},
                                    {"type": "special", "options": {"match": "null", "result": {"text": "(not set)"}}}]},
                                    {"id": "unit", "value": "none"}]},
                                {"matcher": {"id": "byName", "options": "in the band"},
                                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": IN_COLOR}}]},
                                {"matcher": {"id": "byName", "options": "everything else"},
                                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": OUT_COLOR}}]}]},
            "options": {"orientation": "horizontal" if kind == "str" else "vertical", "xField": "value",
                        "groupWidth": 0.75, "barWidth": 0.9, "showValue": "never", "stacking": "none",
                        "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi"}, "xTickLabelMaxLength": 48, "fullHighlight": False,
                        "xTickLabelRotation": 0 if kind == "str" else -45, "xTickLabelSpacing": 0}}


# -- BubbleUp ranking: every attribute's values, the attributes that differ most first ----------------------------
# compare() returns one column per attribute; a server-side SQL expression unpivots the listed ones, turns counts into
# shares of the band and of everything else, scores each attribute by its biggest gap, and keeps the top attributes
# (top values each), biggest gap first. SQL fails on a column that isn't there, so list only attributes this kind of
# span always carries.
RANK_BACKEND = [("Route", "span.http.route"), ("Page", "span.ce.page"), ("Catalog", "span.ce.catalog"),
                ("Course", "span.ce.course.key"), ("Status", "span.http.response.status_code"), ("User", "span.user.id")]
RANK_BROWSER = [("Page", "span.ce.page"), ("Catalog", "span.ce.catalog"), ("Hard or soft", "span.ce.page_view.kind"),
                ("Entry page", "span.ce.entry_page"), ("User", "span.user.id")]


def ranking_sql(attrs, top_attrs=5, per_attr=4):
    rows = "\n UNION ALL ".join(
        f"SELECT '{lab}' AS attr, `{col}` AS val, __meta_type AS t, __value__ AS n FROM A WHERE `{col}` IS NOT NULL"
        for lab, col in attrs)
    return f"""WITH r AS ({rows}),
tot AS (SELECT attr, t, n AS total FROM r WHERE t IN ('"baseline_total"', '"selection_total"') AND val = '"nil"'),
v AS (SELECT attr, val, SUM(CASE WHEN t = '"selection"' THEN n ELSE 0 END) AS sel,
             SUM(CASE WHEN t = '"baseline"' THEN n ELSE 0 END) AS base
      FROM r WHERE t IN ('"selection"', '"baseline"') GROUP BY attr, val),
s AS (SELECT v.attr, v.val, v.sel / ts.total AS in_band, v.base / tb.total AS outside FROM v
      JOIN tot ts ON ts.attr = v.attr AND ts.t = '"selection_total"'
      JOIN tot tb ON tb.attr = v.attr AND tb.t = '"baseline_total"'),
score AS (SELECT attr, MAX(ABS(in_band - outside)) AS gap FROM s GROUP BY attr),
ranked AS (SELECT s.attr, s.val, s.in_band, s.outside, score.gap,
           DENSE_RANK() OVER (ORDER BY score.gap DESC, s.attr) AS attr_rank,
           ROW_NUMBER() OVER (PARTITION BY s.attr ORDER BY ABS(s.in_band - s.outside) DESC) AS val_rank
           FROM s JOIN score ON score.attr = s.attr)
SELECT CONCAT(attr, ':  ', CASE WHEN val = '"nil"' THEN '(not set)' ELSE REPLACE(val, '"', '') END) AS value,
       in_band AS `in the band`, outside AS `everything else`
FROM ranked WHERE attr_rank <= {top_attrs} AND val_rank <= {per_attr}
ORDER BY gap DESC, attr, ABS(in_band - outside) DESC"""


def ranking_panel(attrs, y, title):
    return {"id": next(_ids), "type": "barchart", "title": title, "datasource": TEMPO,
            "description": "BubbleUp: for each attribute, the share of spans in the band (orange) and of everything else "
                           "(gray) per value. Attributes are ordered by their biggest gap, so the ones that best explain "
                           "the band come first (top 5 attributes, top 4 values each). Built from TraceQL compare() and a "
                           "server-side SQL expression",
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 13},
            "targets": [dict(q(f"{base} | compare({{{band}}}, 10)", "instant"), refId="A", hide=True),
                        {"refId": "B", "datasource": EXPR, "type": "sql", "expression": ranking_sql(attrs)}],
            "fieldConfig": {"defaults": {"unit": "percentunit", "decimals": 0, "min": 0, "max": 1,
                                         "custom": {"fillOpacity": 85, "lineWidth": 0}},
                            "overrides": [
                                {"matcher": {"id": "byName", "options": "in the band"},
                                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": IN_COLOR}}]},
                                {"matcher": {"id": "byName", "options": "everything else"},
                                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": OUT_COLOR}}]}]},
            "options": {"orientation": "horizontal", "xField": "value", "groupWidth": 0.75, "barWidth": 0.9,
                        "showValue": "never", "stacking": "none", "xTickLabelMaxLength": 60,
                        "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi"}}}


def attr_section(title, attrs, y, collapsed, rank=None):
    top = [ranking_panel(rank, y + 1, "Most different first: each attribute's values, the attribute with the biggest gap on top")] if rank else []
    y0 = y + 1 + (13 if rank else 0)
    ps = top + [attr_panel(a, k, t, 12 * (i % 2), y0 + 9 * (i // 2)) for i, (a, k, t) in enumerate(attrs)]
    row = {"id": next(_ids), "type": "row", "title": title, "collapsed": collapsed, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
           "panels": ps if collapsed else []}
    return [row] + ([] if collapsed else ps)


panels += attr_section("What the band has in common: backend requests (orange = in the band, gray = everything else)",
                       BACKEND_ATTRS, 38, False, RANK_BACKEND)
panels += attr_section("What the band has in common: page views (choose Spans: Page views)", BROWSER_ATTRS, 98, True, RANK_BROWSER)

dash = {
    "title": "Studio OTel POC: compare a selection",
    "uid": "studio-otel-bubbleup",
    "time": {"from": "now-3h", "to": "now"},
    "timezone": "browser",
    "tags": ["studio", "otel", "poc"],
    "templating": {"list": [
        custom("spans", "Spans", SPANS, SPANS[0][1]),
        custom("y", "Y-axis", Y, "duration"),
        textbox("lo", "From", "1s", "Lower edge of the band on the y-axis (duration: 500ms, 2s; others: a number)"),
        textbox("hi", "To", "1h", "Upper edge of the band"),
        *[{"name": f, "label": f.capitalize(), "type": "adhoc", "datasource": TEMPO, "filters": [],
           "description": "One condition per bar: an attribute (type to search), an operator, a value"} for f in FILTERS],
        dict(custom("by", "Group by", GROUP_BY, "span.ce.page"), allowCustomValue=True,
             description="The attribute the two breakdown panels group by; pick one or type any attribute"),
    ]},
    "panels": panels,
}
print(json.dumps(dash, indent=1, ensure_ascii=False))
