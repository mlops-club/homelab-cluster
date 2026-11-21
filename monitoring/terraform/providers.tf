# Purpose: Configure the Grafana provider for the homelab Grafana Cloud stack
# Scope: No secrets in code. The provider reads GRAFANA_URL, GRAFANA_AUTH, GRAFANA_SM_URL and
#   GRAFANA_SM_ACCESS_TOKEN from the environment; ./tf maps the repo's .env names onto them.
#   stack_id is required by app-platform resources such as secure values (secrets.tf)

variable "grafana_stack_id" {
  type        = number
  description = "Numeric Grafana Cloud stack ID (GRAFANA_STACK_ID in .env)"
}

provider "grafana" {
  stack_id = var.grafana_stack_id
}
