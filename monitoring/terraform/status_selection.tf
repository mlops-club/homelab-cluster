# Purpose: Queries for the "selected period" panels inside each status-dashboard toggle: run log and comparison
# Scope: Shared by status_dashboard.tf. The selection is the dashboard time range: clicking a bar sets it to
#   that run (30 min around the bar), dragging across the bars sets it to the dragged period
# Overview: The "now" and "uptime, 24 h" stats are pinned to the last 24 h. Grafana ignores a panel's relative
#   time override once the dashboard range is absolute, so the bar charts zoom to the selection (zoom out or
#   press back to return). Panels in the toggle follow the selection: the run log shows only the selected
#   runs, and the comparison table puts the selected period's averages next to the 24 h up to it

locals {
  logs = { type = "loki", uid = "grafanacloud-logs" }

  # One readable line per log entry; SM's agent logs in logfmt, k6 "check result" lines carry check, group, value.
  # Public probes are named (Oregon, Ohio); the tailnet probe is the only private one, so it goes unnamed
  run_log_format = join("", [
    "{{ if ne .probe \"homelab-tailnet-laptop\" }}[{{ .probe }}] {{ end }}",
    "{{ if eq .msg \"check result\" }}{{ if eq .value \"1\" }}✓{{ else }}✗{{ end }} {{ with trimPrefix \"::\" .group }}{{ . }}: {{ end }}{{ .check }}",
    "{{ else if eq .msg \"Check succeeded\" }}PASSED in {{ .duration_seconds }} s",
    "{{ else if eq .msg \"Check failed\" }}FAILED after {{ .duration_seconds }} s",
    "{{ else if eq .msg \"Beginning check\" }}▶ Beginning check",
    "{{ else }}{{ .msg }}{{ if .error }}: {{ .error }}{{ end }}{{ if .key }} ({{ .key }}){{ end }}{{ end }}",
  ])
  # LogQL run log for one job
  run_log_expr = "{job=\"%s\"} | logfmt | msg!~\"Check will be run.*\" | line_format \"${replace(local.run_log_format, "\"", "\\\"")}\""

  # Average of each measure over RANGE, one series per `item` label. Login checks have steps (k6 groups, ms);
  # the browser check has web vitals (ms). Measures a check doesn't emit simply return nothing
  compare_items = join(" or ", [
    "label_replace(avg(avg_over_time(probe_duration_seconds{job=\"JOB\"}[RANGE])), \"item\", \"whole run\", \"\", \"\")",
    "label_replace(avg by (group) (avg_over_time(probe_group_duration{job=\"JOB\"}[RANGE])) / 1000, \"item\", \"step: $1\", \"group\", \"::(.*)\")",
    "label_replace(avg(avg_over_time(probe_browser_web_vital_ttfb{job=\"JOB\"}[RANGE])) / 1000, \"item\", \"time to first byte\", \"\", \"\")",
    "label_replace(avg(avg_over_time(probe_browser_web_vital_fcp{job=\"JOB\"}[RANGE])) / 1000, \"item\", \"first contentful paint\", \"\", \"\")",
    "label_replace(avg(avg_over_time(probe_browser_web_vital_lcp{job=\"JOB\"}[RANGE])) / 1000, \"item\", \"largest contentful paint\", \"\", \"\")",
  ])
  compare_expr = { for s in local.status_services : s.job => {
    selected = "sum by (item) (${replace(replace(local.compare_items, "JOB", s.job), "RANGE", "$__range")})"
    baseline = "sum by (item) (${replace(replace(local.compare_items, "JOB", s.job), "RANGE", "24h")})"
  } }
}
