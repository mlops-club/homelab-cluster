# Purpose: Private Synthetic Monitoring probes that run inside the tailnet
# Scope: One probe per location. homelab-cluster runs as a pod in the cluster (apps/sm-probe) and carries
#   every private check (it replaced the POC probe homelab-tailnet-laptop, which ran in Podman on a laptop)
# Overview: A probe is only a registration: name, map location and labels. Grafana returns a token; the agent
#   holding that token runs the checks assigned to the probe. Latitude, longitude and region only place the
#   probe on Grafana's map; where checks really run from is wherever the agent container runs

resource "grafana_synthetic_monitoring_probe" "cluster" {
  name      = "homelab-cluster"
  latitude  = 40.39 # Utah County, rounded
  longitude = -111.85
  region    = "AMER"
  labels = {
    network = "tailnet"
    host    = "cluster"
  }
}

output "cluster_probe_token" {
  description = "API_TOKEN for the synthetic-monitoring-agent pod (apps/sm-probe/deploy.sh reads it)"
  value       = grafana_synthetic_monitoring_probe.cluster.auth_token
  sensitive   = true
}
