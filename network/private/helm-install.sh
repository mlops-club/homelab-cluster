#!/bin/bash -euox pipefail

# Main installation script for private network components
# Installs: cert-manager → reflector → tailscale → external-dns → wildcard certificate → traefik-private

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

echo "=========================================="
echo "Installing Private Network Components"
echo "=========================================="

echo ""
echo "Step 1/6: Installing cert-manager..."
"${SCRIPT_DIR}/cert-manager/install-cert-manager.sh"

echo ""
echo "Step 2/6: Installing Reflector..."
"${SCRIPT_DIR}/reflector/helm-install.sh"

echo ""
echo "Step 3/6: Installing Tailscale Operator..."
"${SCRIPT_DIR}/tailscale/helm-install.sh"

echo ""
echo "Step 4/6: Installing External-DNS..."
"${SCRIPT_DIR}/external-dns/helm-install.sh"

echo ""
echo "Step 5/6: Creating wildcard certificate for *.priv.mlops-club.org..."
kubectl apply -f "${SCRIPT_DIR}/traefik/priv-wildcard-certificate.yaml"

# Wait for certificate to be ready
echo "Waiting for certificate to be ready..."
kubectl wait --for=condition=Ready certificate/priv-wildcard -n traefik-private --timeout=300s || echo "Certificate may take a moment to become ready"

echo ""
echo "Step 6/6: Installing Traefik Private..."
"${SCRIPT_DIR}/traefik/helm-install.sh"

echo ""
echo "=========================================="
echo "Private network components installed successfully!"
echo "=========================================="

