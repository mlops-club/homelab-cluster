# Purpose: Unauthenticated health checks against private services, run from the tailnet probe
# Scope: Test 1 of the Grafana POC (does a private probe reach *.priv.mlops-club.org?).
#   Smoke tests with logins replace these once monitoring users exist

locals {
  private_health = {
    jellyfin = "https://jellyfin.priv.mlops-club.org/health"
    immich   = "https://photos.priv.mlops-club.org/api/server/ping"
    harbor   = "https://cr.priv.mlops-club.org/api/v2.0/health"
    k2       = "https://k2.priv.mlops-club.org/health"
  }
}

resource "grafana_synthetic_monitoring_check" "private_health" {
  for_each  = local.private_health
  job       = "${each.key}-health"
  target    = each.value
  enabled   = true
  frequency = 1200000 # 20 min: 2,232 runs/month per check (1 min = 44,640)
  timeout   = 5000
  probes    = [grafana_synthetic_monitoring_probe.cluster.id]
  labels = {
    service = each.key
    kind    = "health"
  }
  settings {
    http {
      method             = "GET"
      valid_status_codes = [200]
      fail_if_not_ssl    = true
    }
  }
}
