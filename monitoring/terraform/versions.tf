# Purpose: Pin Terraform and the Grafana provider for the homelab monitoring stack
# Scope: Provider requirements and the state backend; credentials come from environment variables (see providers.tf)
# Overview: State lives in the cluster as Secret terraform-state/tfstate-default-grafana-monitoring, locked with a
#   Lease of the same name (kubernetes backend). It holds probe tokens, so only cluster admins can read it. The
#   kubeconfig's current context must point at the homelab cluster (~/.kube/config locally, a CI kubeconfig in Actions)

terraform {
  backend "kubernetes" {
    secret_suffix = "grafana-monitoring"
    namespace     = "terraform-state"
    config_path   = "~/.kube/config"
  }
  required_version = ">= 1.11" # write-only arguments (secrets.tf)
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.26" # grafana_apps_secret_securevalue_v1beta1
    }
  }
}
