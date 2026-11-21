# Purpose: Read-only service account for mcp-grafana, so AI-assisted investigations can't change the stack
# Scope: Grafana POC test 8. The token lands in Terraform state (gitignored), never in the repo

resource "grafana_service_account" "mcp" {
  name        = "homelab-mcp"
  role        = "Viewer"
  is_disabled = false
}

resource "grafana_service_account_token" "mcp" {
  name               = "homelab-mcp"
  service_account_id = grafana_service_account.mcp.id
}

output "mcp_token" {
  value     = grafana_service_account_token.mcp.key
  sensitive = true
}
