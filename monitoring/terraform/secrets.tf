# Purpose: Grafana secret-store entries holding the monitoring users' passwords for the login checks
# Scope: One secure value per app, decryptable only by Synthetic Monitoring. Scripts read them with
#   `await secrets.get('<app>-monitor-password')` (k6/secrets)
# Overview: Values come from ~/credentials/homelab-monitoring.env through ./tf as an ephemeral variable,
#   and `value` is write-only, so passwords never land in Terraform state or the repo. Rotating a password
#   means updating the credentials file and the app, then `./tf apply -replace=...` for that entry

variable "monitor_passwords" {
  type        = map(string)
  sensitive   = true
  ephemeral   = true
  description = "Monitoring-user passwords keyed by app (set by ./tf from ~/credentials)"
}

locals {
  monitored_apps = toset(["jellyfin", "navidrome", "immich", "audiobookshelf"])
}

resource "grafana_apps_secret_securevalue_v1beta1" "monitor_password" {
  for_each = local.monitored_apps
  metadata {
    uid = "${each.key}-monitor-password"
  }
  spec {
    description = "${each.key} monitor pw"
    value       = var.monitor_passwords[each.key]
    decrypters  = ["synthetic-monitoring"]
  }
}
