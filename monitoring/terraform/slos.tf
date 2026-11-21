# Purpose: Availability SLOs computed from synthetic check results, with burn-rate alerts
# Scope: Grafana POC test 4 (window vs 14-day retention, burn-rate alerting)

resource "grafana_slo" "jellyfin_availability" {
  name        = "Jellyfin availability"
  description = "Share of synthetic health checks from the tailnet probe that succeed"
  query {
    type = "ratio"
    ratio {
      success_metric  = "probe_all_success_sum{job=\"jellyfin-health\"}"
      total_metric    = "probe_all_success_count{job=\"jellyfin-health\"}"
      group_by_labels = []
    }
  }
  objectives {
    value  = 0.999
    window = "30d"
  }
  destination_datasource {
    uid = "grafanacloud-prom"
  }
  label {
    key   = "service"
    value = "jellyfin"
  }
  alerting {
    fastburn {
      label {
        key   = "team"
        value = "homelab"
      }
      annotation {
        key   = "summary"
        value = "Jellyfin is burning its error budget fast"
      }
    }
    slowburn {
      label {
        key   = "team"
        value = "homelab"
      }
      annotation {
        key   = "summary"
        value = "Jellyfin is burning its error budget slowly"
      }
    }
  }
}
