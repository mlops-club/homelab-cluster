# Purpose: Outside-in browser checks from Grafana public probes (the only outside-in layer)
# Scope: Grafana POC test 3. Browser runs come from the 10k/month pool: 2 probes x 15 min = 5,952

data "grafana_synthetic_monitoring_probes" "public" {}

resource "grafana_synthetic_monitoring_check" "audiobookshelf_browser" {
  job       = "audiobookshelf-browser"
  target    = "https://books.mlops-club.org/login"
  enabled   = true
  frequency = 900000 # 15 min
  timeout   = 60000
  probes = [
    data.grafana_synthetic_monitoring_probes.public.probes.Oregon,
    data.grafana_synthetic_monitoring_probes.public.probes.Ohio,
  ]
  labels = {
    service = "audiobookshelf"
    kind    = "browser"
  }
  settings {
    browser {
      script = file("${path.module}/../checks/audiobookshelf-browser.js")
    }
  }
}
