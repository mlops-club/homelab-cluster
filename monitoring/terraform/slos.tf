# Purpose: Availability SLOs computed from synthetic check results, where a missing result counts as a failure
# Scope: One SLO per listener-facing service (status_dashboard.tf rows), 99.9 % over 14 days, with Grafana's
#   generated fast- and slow-burn alerts routed to team=homelab (Discord, notifications.tf)
# Overview: SLI = passed runs / EXPECTED runs, not / received runs. Grafana SLO evaluates the query in 5-minute
#   buckets ($__rate_interval = 5m) and adds the buckets up over each window:
#     numerator   sum_over_time(probe_success[5m]) = runs that passed in the bucket ("or vector(0)": a silent
#                 bucket counts as 0 passes instead of disappearing)
#     denominator sum_over_time(vector(e)[5m:5m]) = runs the schedule promises in the bucket, e = L x 300 s / interval
#   A probe or network outage therefore lowers the SLI like a real outage. Received-based ratios
#   (probe_all_success_sum / _count) skip silent buckets and would read 100 % while nothing is checked.
#   Math walkthrough: .ai/docs/adr/0001-outside-in-monitoring/decision.md

locals {
  # job = check job name; locations = probes running it; interval_s = check frequency in seconds
  slo_services = {
    jellyfin            = { name = "Jellyfin", job = "jellyfin-login", locations = 1, interval_s = 900 }
    navidrome           = { name = "Navidrome", job = "navidrome-login", locations = 1, interval_s = 900 }
    immich              = { name = "Photos (Immich)", job = "immich-login", locations = 1, interval_s = 900 }
    audiobookshelf      = { name = "Audiobookshelf", job = "audiobookshelf-login", locations = 2, interval_s = 900 }
    golden-rules-studio = { name = "Golden Rules Studio", job = "golden-rules-studio-health", locations = 2, interval_s = 900 }
    harbor              = { name = "Harbor", job = "harbor-health", locations = 1, interval_s = 300 }
    k2                  = { name = "K2", job = "k2-health", locations = 1, interval_s = 300 }
  }
  slo_objective = 0.999
  slo_window    = "14d" # trial retention is 14 days; longer windows would average over missing history
  # Expected-runs SLI, shared with the dashboard's math panels
  slo_query = { for k, s in local.slo_services : k => format(
    "(sum(sum_over_time(probe_success{job=\"%s\"}[$__rate_interval])) or vector(0)) / sum(sum_over_time(vector(%s)[$__rate_interval:5m]))",
    s.job, format("%.6f", s.locations * 300 / s.interval_s)
  ) }
}

resource "grafana_slo" "availability" {
  for_each    = local.slo_services
  name        = "${each.value.name} availability"
  description = "Share of expected ${each.value.job} runs (${each.value.locations} location(s), every ${each.value.interval_s / 60} min) that passed; a run that never reported counts as failed"
  query {
    type = "freeform"
    freeform {
      query = local.slo_query[each.key]
    }
  }
  objectives {
    value  = local.slo_objective
    window = local.slo_window
  }
  destination_datasource {
    uid = "grafanacloud-prom"
  }
  label {
    key   = "service"
    value = each.key
  }
  alerting {
    fastburn {
      label {
        key   = "team"
        value = "homelab"
      }
      annotation {
        key   = "summary"
        value = "${each.value.name} is burning its error budget fast"
      }
    }
    slowburn {
      label {
        key   = "team"
        value = "homelab"
      }
      annotation {
        key   = "summary"
        value = "${each.value.name} is burning its error budget slowly"
      }
    }
  }
}
