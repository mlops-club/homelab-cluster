# Purpose: Pin Terraform and the Grafana provider for the homelab monitoring stack
# Scope: Provider requirements only; credentials come from environment variables (see providers.tf)

terraform {
  required_version = ">= 1.11" # write-only arguments (secrets.tf)
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.26" # grafana_apps_secret_securevalue_v1beta1
    }
  }
}
