#!/bin/bash -euox pipefail

# Main orchestrator script to install all network components

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${PROJECT_ROOT}/.env"

echo "Installing Cloudflare Tunnel Ingress Controller..."
"${SCRIPT_DIR}/cloudflare-tunnel-ingress-controller/helm-install.sh"

echo "Installing Tailscale Operator..."
"${SCRIPT_DIR}/tailscale/helm-install.sh"

echo "Installing External DNS..."
"${SCRIPT_DIR}/external-dns/helm-install.sh"

echo "All network components installed successfully!"

