# Purpose: Private Synthetic Monitoring probes that run inside the tailnet
# Scope: One probe per location. The POC probe runs on a laptop; the cluster probe replaces it later

resource "grafana_synthetic_monitoring_probe" "tailnet_laptop" {
  name      = "homelab-tailnet-laptop"
  latitude  = 40.39 # Utah County, rounded
  longitude = -111.85
  region    = "AMER"
  labels = {
    network = "tailnet"
    host    = "laptop"
  }
}

output "tailnet_laptop_probe_token" {
  description = "API_TOKEN for the synthetic-monitoring-agent on the laptop"
  value       = grafana_synthetic_monitoring_probe.tailnet_laptop.auth_token
  sensitive   = true
}
