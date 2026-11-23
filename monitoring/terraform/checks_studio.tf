# Purpose: Outside-in health check for Golden Rules Studio's public address
# Scope: Studio is the one app in the Studio/Harbor/K2 group with a public URL, so it is checked from Grafana's
#   public probes like Audiobookshelf. Harbor and K2 are private and checked from the cluster probe (checks_health.tf)
# Overview: GET /api/health must return 200 over valid TLS. 20 min x 2 locations = 4,464 API runs/month

resource "grafana_synthetic_monitoring_check" "studio_health" {
  job       = "golden-rules-studio-health"
  target    = "https://golden-rules-studio.mlops-club.org/api/health"
  enabled   = true
  frequency = 1200000 # 20 min
  timeout   = 10000
  probes = [
    data.grafana_synthetic_monitoring_probes.public.probes.Oregon,
    data.grafana_synthetic_monitoring_probes.public.probes.Ohio,
  ]
  labels = {
    service = "golden-rules-studio"
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
