# Purpose: k6 scripted checks run by the tailnet probe; the same files run locally with `k6 run`
# Scope: Grafana POC test 2 (multi-step check counting, API smoke tests)

resource "grafana_synthetic_monitoring_check" "media_health" {
  job       = "media-health"
  target    = "https://jellyfin.priv.mlops-club.org" # label only; the script defines the requests
  enabled   = true
  frequency = 1200000 # 20 min
  timeout   = 30000
  probes    = [grafana_synthetic_monitoring_probe.cluster.id]
  labels = {
    service = "media"
    kind    = "scripted"
  }
  settings {
    scripted {
      script = file("${path.module}/../checks/media-health.js")
    }
  }
}
