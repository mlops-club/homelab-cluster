# Purpose: Availability SLOs computed from synthetic check results, where a missing result counts as a failure
# Scope: One SLO per listener-facing service (status_dashboard.tf rows), 99.9 % over 14 days, with Grafana's
#   generated fast- and slow-burn alerts routed to team=homelab (Discord, notifications.tf)
# Overview: The SLI counts 5-minute slots, one per probe location: SLI = passing slots / EXPECTED slots, never
#   / received. The SM agent re-publishes each check's latest result about once a minute, so probe_success is a
#   state that holds between runs; while a probe or network is down, no samples arrive and the slot is empty.
#   Grafana SLO evaluates the query in 5-minute buckets ($__rate_interval = 5m) and adds the buckets up:
#     numerator   sum over locations of avg_over_time(probe_success[5m]): share of the slot each location reported
#                 passing; "or vector(0)" turns an empty slot into 0 instead of dropping it
#     denominator sum_over_time(vector(L)[5m:5m]) = L slots per bucket, whether or not anything arrived
#   A probe or network outage therefore lowers the SLI like a real outage, and a failed 15-minute run counts for
#   the ~15 minutes its result stands. Counting samples would overcount (one run = many samples), and
#   increase() of the run counter loses runs at bucket edges; received-based ratios
#   (probe_all_success_sum / _count) skip silent buckets and read 100 % while nothing is checked.
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
  # Slot-based SLI (see header), shared with the dashboards' math table and uptime stats
  slot_good = "sum_over_time((sum(avg_over_time(probe_success{job=\"%s\"}[5m])) or vector(0))[%s:5m])"
  slot_all  = "sum_over_time(vector(%d)[%s:5m])"
  slo_query = { for k, s in local.slo_services : k => format("%s / %s",
    format(local.slot_good, s.job, "$__rate_interval"), format(local.slot_all, s.locations, "$__rate_interval")
  ) }
}

resource "grafana_slo" "availability" {
  for_each    = local.slo_services
  name        = "${each.value.name} availability"
  description = "Share of expected 5-minute slots (${each.value.locations} location(s)) in which ${each.value.job} reported passing; a slot with no result counts as failed"
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
