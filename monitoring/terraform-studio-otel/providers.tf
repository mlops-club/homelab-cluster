# Purpose: Grafana provider for the Studio OTel POC
# Scope: No secrets in code: GRAFANA_URL and GRAFANA_AUTH come from the environment (./tf maps the repo .env onto
#   them, like monitoring/terraform/tf)
provider "grafana" {}
