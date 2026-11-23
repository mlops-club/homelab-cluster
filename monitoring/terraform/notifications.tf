# Purpose: Deliver homelab alerts to Discord #homelab-alerts; everything else stays on the silent default
# Scope: Grafana POC test 6. Only rules labelled team=homelab are routed, which keeps Grafana's built-in
#   trial rules (e.g. asserts_up) out of the channel
# Overview: The webhook URL comes from ~/credentials/homelab-alerting.env via ./tf. It is stored in
#   Terraform state (a Secret in the cluster, ADR 0003), like the other tokens. Routing: ADR 0004. grafana_notification_policy owns the whole tree

variable "discord_alerts_webhook_url" {
  type        = string
  sensitive   = true
  description = "Discord webhook for #homelab-alerts (set by ./tf from ~/credentials)"
}

resource "grafana_contact_point" "discord" {
  name = "homelab-discord"
  discord {
    url                     = var.discord_alerts_webhook_url
    use_discord_username    = false
    disable_resolve_message = false
  }
}

resource "grafana_notification_policy" "root" {
  contact_point = "empty"
  group_by      = ["grafana_folder", "alertname"]

  policy {
    matcher {
      label = "team"
      match = "="
      value = "homelab"
    }
    contact_point   = grafana_contact_point.discord.name
    group_by        = ["alertname", "service"]
    group_wait      = "30s"
    group_interval  = "5m"
    repeat_interval = "4h"
  }
}
