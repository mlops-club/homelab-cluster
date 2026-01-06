#!/bin/bash -euox pipefail

# Main orchestrator script to install all network components

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${PROJECT_ROOT}/.env"

echo "Installing Cloudflare Tunnel Ingress Controller..."
"${SCRIPT_DIR}/public/cloudflare-tunnel-ingress-controller/helm-install.sh"

echo "Installing Tailscale Operator..."
"${SCRIPT_DIR}/private/tailscale/helm-install.sh"

echo "Installing External DNS..."
"${SCRIPT_DIR}/private/external-dns/helm-install.sh"

echo "Installing Traefik Public..."
"${SCRIPT_DIR}/public/traefik/helm-install.sh"

echo "All network components installed successfully!"

