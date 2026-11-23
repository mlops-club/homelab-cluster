# Purpose: Uptime per service, computed from synthetic check results, where a missing result counts as down
# Scope: One Grafana SLO per service (status_dashboard.tf rows), window 14 days. The dashboards show only uptime,
#   downtime and how much of the window is measured; the 95 % objective exists because Grafana SLO requires one, and
#   drives the generated fast- and slow-burn alerts routed to team=homelab (ADR 0004, notifications.tf)
# Overview: Uptime counts readings. Every 5 minutes, each probe location gives one reading: the state of its latest
#   check result. The SM agent re-publishes each check's latest result about once a minute, so probe_success holds
#   between runs (a 20-minute run is read 4 times); while a probe or network is down, nothing arrives.
#   Grafana SLO evaluates the query in 5-minute buckets ($__rate_interval = 5m) and adds the buckets up:
#     readings up        sum over locations of avg_over_time(probe_success[5m]); "max by (probe)" keeps one
#                        series per location (editing a check starts a new config_version series that overlaps the
#                        old one for a few minutes); "or vector(0)" turns an empty bucket into 0 instead of dropping it
#     readings expected  sum_over_time(vector(locations)[5m:5m]): one per location per bucket, whatever arrived
#   A probe or network outage therefore lowers uptime like a real outage. Counting samples would overcount (one run
#   = many samples), increase() of the run counter loses runs at bucket edges, and ratios over received results
#   (probe_all_success_sum / _count) read 100 % while nothing is checked.
#   The dashboards compute uptime from the raw results with the same readings (status_dashboard.tf); these SLO
#   resources exist for their burn-rate alerts. Math walkthrough: .ai/docs/adr/0001-outside-in-monitoring/decision.md

locals {
  # job = check job name; locations = probes running it; interval_s = check frequency in seconds
  slo_services = {
    jellyfin            = { name = "Jellyfin", job = "jellyfin-login", locations = 1, interval_s = 1200 }
    navidrome           = { name = "Navidrome", job = "navidrome-login", locations = 1, interval_s = 1200 }
    immich              = { name = "Photos (Immich)", job = "immich-login", locations = 1, interval_s = 1200 }
    audiobookshelf      = { name = "Audiobookshelf", job = "audiobookshelf-login", locations = 2, interval_s = 1200 }
    golden-rules-studio = { name = "Golden Rules Studio", job = "golden-rules-studio-health", locations = 2, interval_s = 1200 }
    harbor              = { name = "Harbor", job = "harbor-health", locations = 1, interval_s = 1200 }
    k2                  = { name = "K2", job = "k2-health", locations = 1, interval_s = 1200 }
  }
  slo_objective = 0.95  # required by Grafana SLO; only the burn-rate alerts use it
  slo_window    = "14d" # trial retention is 14 days; longer windows would average over missing history
  # Readings (see header), shared with the dashboards' uptime table and 24 h uptime stats
  readings_up       = "sum_over_time((sum(max by (probe) (avg_over_time(probe_success{job=\"%s\"}[5m]))) or vector(0))[%s:5m])"
  readings_expected = "sum_over_time(vector(%d)[%s:5m])"
  # Readings expected over a range of N five-minute periods, counted from the check's first result in the last 14 days
  # (a new check isn't charged for the days before it existed). %d locations, %s job, %s = N periods
  # ("288" = 24 h of 5-minute periods, "14 * 288" = 14 days)
  readings_expected_since_first = "%d * clamp_max(ceil((time() - min(min_over_time(timestamp(probe_success{job=\"%s\"})[14d:5m]))) / (5 * 60)), %s)"
  slo_query = { for k, s in local.slo_services : k => format("%s / %s",
    format(local.readings_up, s.job, "$__rate_interval"), format(local.readings_expected, s.locations, "$__rate_interval")
  ) }
}

resource "grafana_slo" "availability" {
  for_each    = local.slo_services
  name        = "${each.value.name} availability"
  description = "Uptime: share of expected 5-minute readings (${each.value.locations} location(s)) in which ${each.value.job} reported passing; a reading with no result counts as down"
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
