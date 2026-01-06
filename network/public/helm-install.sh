#!/bin/bash -euox pipefail

# Main installation script for public network components
# Installs: Cloudflare Tunnel Ingress Controller → Traefik Public

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

echo "=========================================="
echo "Installing Public Network Components"
echo "=========================================="

echo ""
echo "Step 1/2: Installing Cloudflare Tunnel Ingress Controller..."
"${SCRIPT_DIR}/cloudflare-tunnel-ingress-controller/helm-install.sh"

echo ""
echo "Step 2/2: Installing Traefik Public..."
"${SCRIPT_DIR}/traefik/helm-install.sh"

echo ""
echo "=========================================="
echo "Public network components installed successfully!"
echo "=========================================="

