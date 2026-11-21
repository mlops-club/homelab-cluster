# Purpose: Dead man's switch inside Grafana: alert when the tailnet probe stops reporting
# Scope: Grafana POC test 5. A whole-cluster (or laptop) outage shows up as missing data, so
#   no_data_state = Alerting turns silence into a page

resource "grafana_folder" "homelab_alerts" {
  title = "Homelab alerts"
}

resource "grafana_rule_group" "probe_heartbeat" {
  name             = "probe-heartbeat"
  folder_uid       = grafana_folder.homelab_alerts.uid
  interval_seconds = 60

  rule {
    name           = "Tailnet probe is silent"
    condition      = "B"
    for            = "2m"
    no_data_state  = "Alerting"
    exec_err_state = "Alerting"
    labels         = { severity = "critical", service = "probe", team = "homelab" }
    annotations = {
      summary = "No results from the tailnet probe: the probe host, the cluster network or the tailnet is down"
    }

    data {
      ref_id         = "A"
      datasource_uid = "grafanacloud-prom"
      relative_time_range {
        from = 600
        to   = 0
      }
      model = jsonencode({
        refId   = "A"
        expr    = "count(probe_success{probe=\"homelab-tailnet-laptop\"})"
        instant = true
      })
    }
    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      relative_time_range {
        from = 0
        to   = 0
      }
      model = jsonencode({
        refId      = "B"
        type       = "math"
        expression = "$A < 1"
      })
    }
  }
}
