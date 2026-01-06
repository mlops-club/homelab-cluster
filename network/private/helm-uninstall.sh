#!/bin/bash -euox pipefail

# Main uninstallation script for private network components
# Uninstalls: traefik-private → external-dns → tailscale-operator → cert-manager

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=========================================="
echo "Uninstalling Private Network Components"
echo "=========================================="

echo ""
echo "Step 1/4: Uninstalling Traefik Private..."
helm uninstall traefik-private -n traefik-private || echo "Traefik Private not found or already uninstalled"

echo ""
echo "Step 2/4: Uninstalling External-DNS..."
helm uninstall external-dns -n traefik-private || echo "External-DNS not found or already uninstalled"

echo ""
echo "Step 3/4: Uninstalling Tailscale Operator..."
helm uninstall tailscale-operator -n traefik-private || echo "Tailscale Operator not found or already uninstalled"

echo ""
echo "Step 4/4: Uninstalling cert-manager..."
helm uninstall cert-manager -n traefik-private || echo "cert-manager not found or already uninstalled"

echo ""
echo "Cleaning up certificates and ClusterIssuers..."
# Delete the wildcard certificate
kubectl delete certificate priv-wildcard -n traefik-private --ignore-not-found || true

# Delete ClusterIssuer (cluster-scoped resource)
kubectl delete clusterissuer letsencrypt-cloudflare --ignore-not-found || true

echo ""
echo "Cleaning up namespaces..."
# Delete namespace if it exists and is empty (or only has finalizers)
kubectl delete namespace traefik-private --ignore-not-found || true

echo ""
echo "Note: cert-manager CRDs are not automatically removed."
echo "To remove cert-manager CRDs, run:"
echo "  kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.crds.yaml"

echo ""
echo "=========================================="
echo "Private network components uninstalled successfully!"
echo "=========================================="

