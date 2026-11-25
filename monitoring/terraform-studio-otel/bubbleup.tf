# Purpose: "Studio OTel POC: compare a selection" dashboard: a BubbleUp-style view over Tempo. Choose the spans, the
#   y-axis attribute (x is time) and a band on it; a TraceQL compare() table lists the attribute values the band has in
#   common, by share of their spans inside it
# Overview: bubbleup.py generates bubbleup.json (variables, heatmap, counts, compare table with its transformations);
#   edit the generator, run `python3 bubbleup.py > bubbleup.json`, then ./tf apply. Grafana's Traces Drilldown app
#   offers the same with a box drawn on the heatmap, for duration only

resource "grafana_dashboard" "studio_otel_bubbleup" {
  folder      = grafana_folder.studio_otel.uid
  config_json = file("${path.module}/bubbleup.json")
}

output "bubbleup_url" { value = grafana_dashboard.studio_otel_bubbleup.url }
