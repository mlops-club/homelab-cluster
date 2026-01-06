#!/bin/bash -euox pipefail

# Main uninstallation script for public network components
# Uninstalls: Traefik Public → Cloudflare Tunnel Ingress Controller

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=========================================="
echo "Uninstalling Public Network Components"
echo "=========================================="

echo ""
echo "Step 1/2: Uninstalling Traefik Public..."
helm uninstall traefik-public -n traefik-public || echo "Traefik Public not found or already uninstalled"

echo ""
echo "Step 2/2: Uninstalling Cloudflare Tunnel Ingress Controller..."
helm uninstall cloudflare-tunnel-ingress-controller -n traefik-public || echo "Cloudflare Tunnel Ingress Controller not found or already uninstalled"

echo ""
echo "Cleaning up namespaces..."
# Delete namespace if it exists and is empty (or only has finalizers)
kubectl delete namespace traefik-public --ignore-not-found || true

echo ""
echo "=========================================="
echo "Public network components uninstalled successfully!"
echo "=========================================="

