# Purpose: Pin Terraform and the Grafana provider for the Studio OTel POC dashboard
# Scope: Provider requirements only. A root of its own (own state), separate from monitoring/terraform/
terraform {
  required_version = ">= 1.11"
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.26"
    }
  }
}
