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

MIN_IN_BAND = 3  # a value seen on one or two spans in the band says little


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


base = f"{{${{spans}} && {ENV}}}"
band = "${y} >= ${lo} && ${y} <= ${hi}"
q = lambda traceql, kind="range": {"refId": "A", "datasource": TEMPO, "queryType": "traceql",
                                   "metricsQueryType": kind, "query": traceql}

intro = """**Compare a selection** (BubbleUp-style). Choose **Spans**, the **Y-axis** attribute and a band on it
(**From** / **To**; duration takes units such as `500ms` or `2s`, other attributes plain numbers). The heatmap shows
every span over time as counts; the dot chart under it shows every span on its own (click one for its trace); the table lists each attribute value with how many of its spans are **in the band** and how many
are **outside it**, sorted by the share in the band. Compare that share with the overall share on the right: a value well
above it is what the selection has in common. To narrow the selection in time, drag on the heatmap (the comparison
then covers that window only). For a box drawn freehand on a duration heatmap, use
[Traces Drilldown](/a/grafana-exploretraces-app/explore) → Duration → select a region → Comparison."""

panels = [
    {"id": 1, "type": "text", "title": "", "gridPos": {"x": 0, "y": 0, "w": 24, "h": 4},
     "options": {"mode": "markdown", "content": intro}},
    {"id": 2, "type": "heatmap", "title": "${y} over time: all ${spans:text}", "datasource": TEMPO,
     "description": "TraceQL histogram_over_time: buckets are powers of two. The band you selected is From..To",
     "gridPos": {"x": 0, "y": 4, "w": 18, "h": 11},
     "targets": [q(f"{base} | histogram_over_time(${{y}})")],
     "fieldConfig": {"defaults": {"unit": "short"}},
     "options": {"calculate": False, "yAxis": {"axisPlacement": "left", "unit": "short"}, "cellGap": 1,
                 "color": {"mode": "scheme", "scheme": "Blues", "scale": "exponential", "exponent": 0.5, "fill": "dark-blue"},
                 "rowsFrame": {"layout": "auto"}, "tooltip": {"mode": "single", "yHistogram": True},
                 "legend": {"show": True}, "exemplars": {"color": "orange"}}},
    {"id": 3, "type": "stat", "title": "In the band", "datasource": TEMPO,
     "gridPos": {"x": 18, "y": 4, "w": 3, "h": 5},
     "targets": [q(f"{{${{spans}} && {ENV} && {band}}} | count_over_time()", "instant")],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "noValue": "0"}}},
    {"id": 4, "type": "stat", "title": "All spans", "datasource": TEMPO,
     "gridPos": {"x": 21, "y": 4, "w": 3, "h": 5},
     "targets": [q(f"{base} | count_over_time()", "instant")],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "short", "decimals": 0, "noValue": "0"}}},
    {"id": 5, "type": "stat", "title": "Overall share in the band", "datasource": TEMPO,
     "description": "In the band / all spans. A value whose share in the table is well above this is overrepresented",
     "gridPos": {"x": 18, "y": 9, "w": 6, "h": 6},
     "targets": [dict(q(f"{{${{spans}} && {ENV} && {band}}} | count_over_time()", "instant"), refId="A", hide=True),
                 dict(q(f"{base} | count_over_time()", "instant"), refId="B", hide=True),
                 # instant TraceQL results carry different timestamps, so reduce each to a number before dividing
                 {"refId": "RA", "datasource": EXPR, "type": "reduce", "expression": "A", "reducer": "last", "hide": True},
                 {"refId": "RB", "datasource": EXPR, "type": "reduce", "expression": "B", "reducer": "last", "hide": True},
                 {"refId": "C", "datasource": EXPR, "type": "math", "expression": "$RA / $RB"}],
     "options": {"colorMode": "none", "graphMode": "none", "textMode": "value", "reduceOptions": {"calcs": ["lastNotNull"]}},
     "fieldConfig": {"defaults": {"unit": "percentunit", "decimals": 1, "noValue": "–"}}},
    {"id": 7, "type": "xychart", "title": "Every span: ${y:text} over time. Click a dot, then a link, for its trace",
     "datasource": TEMPO,
     "description": "TraceQL search, one dot per span (up to 1000 traces, 100 spans each: on a busy range not every span "
                    "is shown, so narrow the time range). Duration is shown in time units. The Tempo panel merges every "
                    "query into one frame, so spans in the band cannot be coloured separately: use the counts and the "
                    "table below for the band",
     "gridPos": {"x": 0, "y": 15, "w": 24, "h": 14},
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
    {"id": 6, "type": "table", "title": "What the band has in common: attribute values by share of their spans in the band",
     "datasource": TEMPO,
     "description": "TraceQL compare(): for each attribute value (top 10 per attribute), spans in the band and outside it. "
                    "Share = in band / (in band + outside). Per-span IDs are hidden",
     "gridPos": {"x": 0, "y": 29, "w": 24, "h": 16},
     "targets": [q(f"{base} | compare({{{band}}}, 10)", "instant")],
     "transformations": [
         {"id": "seriesToRows", "options": {}},
         {"id": "extractFields", "options": {"source": "Metric", "format": "regexp",
          "regExp": r'/\{__meta_type="(?<type>[^"]+)", (?<item>.*)\}/', "replace": False}},
         {"id": "filterByValue", "options": {"type": "exclude", "match": "any", "filters": [
             {"fieldName": "type", "config": {"id": "regex", "options": {"value": ".*_total"}}},
             {"fieldName": "item", "config": {"id": "regex", "options": {"value": NOISE}}}]}},
         {"id": "groupingToMatrix", "options": {"columnField": "type", "rowField": "item", "valueField": "Value",
                                                "emptyValue": "zero"}},
         {"id": "filterByValue", "options": {"type": "include", "match": "any", "filters": [
             {"fieldName": "selection", "config": {"id": "greaterOrEqual", "options": {"value": MIN_IN_BAND}}}]}},
         {"id": "calculateField", "options": {"mode": "reduceRow", "alias": "all",
          "reduce": {"reducer": "sum", "include": ["baseline", "selection"]}}},
         {"id": "calculateField", "options": {"mode": "binary", "alias": "share in band",
          "binary": {"left": {"matcher": {"id": "byName", "options": "selection"}}, "operator": "/",
                     "right": {"matcher": {"id": "byName", "options": "all"}}}}},
         {"id": "organize", "options": {"excludeByName": {"all": True},
          "indexByName": {"item\\type": 0, "share in band": 1, "selection": 2, "baseline": 3},
          "renameByName": {"item\\type": "attribute = value", "selection": "in band", "baseline": "outside band"}}},
         {"id": "sortBy", "options": {"sort": [{"field": "share in band", "desc": True}, {"field": "in band", "desc": True}]}},
     ],
     "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": [
         {"matcher": {"id": "byName", "options": "share in band"}, "properties": [
             {"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 0}, {"id": "max", "value": 1}, {"id": "min", "value": 0},
             {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}},
             {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
         {"matcher": {"id": "byName", "options": "attribute = value"}, "properties": [{"id": "custom.width", "value": 560}]}]},
     "options": {"showHeader": True, "cellHeight": "sm"}},
]

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
    ]},
    "panels": panels,
}
print(json.dumps(dash, indent=1, ensure_ascii=False))
