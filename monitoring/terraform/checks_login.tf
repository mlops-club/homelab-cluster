# Purpose: Per-app login smoke tests (login, browse, read 64 KB of real media) as k6 scripted checks
# Scope: Grafana POC test 9. Private apps run on the tailnet probe; Audiobookshelf runs from public probes
#   through books.mlops-club.org. 15 min each: 3 x 2,976 + 2 x 2,976 = 14,880 API runs/month

locals {
  login_checks = {
    jellyfin  = "https://jellyfin.priv.mlops-club.org"
    navidrome = "https://navidrome.priv.mlops-club.org"
    immich    = "https://photos.priv.mlops-club.org"
  }
}

resource "grafana_synthetic_monitoring_check" "login_private" {
  for_each  = local.login_checks
  job       = "${each.key}-login"
  target    = each.value # label only; the script defines the requests
  enabled   = true
  frequency = 900000 # 15 min
  timeout   = 30000
  probes    = [grafana_synthetic_monitoring_probe.tailnet_laptop.id]
  labels = {
    service = each.key
    kind    = "login"
  }
  settings {
    scripted {
      script = file("${path.module}/../checks/${each.key}-login.js")
    }
  }
  depends_on = [grafana_apps_secret_securevalue_v1beta1.monitor_password]
}

resource "grafana_synthetic_monitoring_check" "login_audiobookshelf" {
  job       = "audiobookshelf-login"
  target    = "https://books.mlops-club.org"
  enabled   = true
  frequency = 900000 # 15 min
  timeout   = 30000
  probes = [
    data.grafana_synthetic_monitoring_probes.public.probes.Oregon,
    data.grafana_synthetic_monitoring_probes.public.probes.Ohio,
  ]
  labels = {
    service = "audiobookshelf"
    kind    = "login"
  }
  settings {
    scripted {
      script = file("${path.module}/../checks/audiobookshelf-login.js")
    }
  }
  depends_on = [grafana_apps_secret_securevalue_v1beta1.monitor_password]
}
