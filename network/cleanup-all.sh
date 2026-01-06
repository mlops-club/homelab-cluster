#!/bin/bash -euox pipefail

# Comprehensive cleanup script for all network components
# This removes all Helm releases, namespaces, and related resources

set -e

echo "=== Cleaning up all network components ==="

# List of Helm releases to uninstall
HELM_RELEASES=(
  "traefik-public:traefik-public"
  "traefik-private:traefik-private"
  "cloudflare-tunnel-ingress-controller:traefik-public"
  "tailscale-operator:traefik-private"
  "external-dns:traefik-private"
  "cert-manager:traefik-private"
)

# Uninstall Helm releases
echo "--- Uninstalling Helm releases ---"
for release_info in "${HELM_RELEASES[@]}"; do
  IFS=':' read -r release_name namespace <<< "$release_info"
  if helm list -n "$namespace" | grep -q "^${release_name}\s"; then
    echo "Uninstalling ${release_name} from namespace ${namespace}..."
    helm uninstall "$release_name" -n "$namespace" || echo "Failed to uninstall ${release_name}, continuing..."
  else
    echo "${release_name} not found in namespace ${namespace}, skipping..."
  fi
done

# Delete example namespaces and their resources
echo "--- Deleting example namespaces ---"
for ns in whoami-public whoami-priv whoami-external whoami-internal; do
  if kubectl get namespace "$ns" &>/dev/null; then
    echo "Deleting namespace ${ns}..."
    kubectl delete namespace "$ns" --wait=true --timeout=60s || echo "Failed to delete namespace ${ns}, continuing..."
  fi
done

# Delete main network namespaces
echo "--- Deleting network namespaces ---"
for ns in traefik-public traefik-private; do
  if kubectl get namespace "$ns" &>/dev/null; then
    echo "Deleting namespace ${ns}..."
    kubectl delete namespace "$ns" --wait=true --timeout=60s || echo "Failed to delete namespace ${ns}, continuing..."
  fi
done

# Clean up ClusterIssuers (cluster-scoped resources)
echo "--- Cleaning up ClusterIssuers ---"
kubectl delete clusterissuer letsencrypt-cloudflare --ignore-not-found=true || true

# Clean up cert-manager CRDs (optional - comment out if you want to keep them)
echo "--- Cleaning up cert-manager CRDs ---"
CERT_MANAGER_VERSION="v1.13.3"
kubectl delete -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.crds.yaml" --ignore-not-found=true || true

# Clean up secrets in traefik-private (external-dns and cert-manager might have created some)
echo "--- Cleaning up secrets ---"
kubectl delete secret cloudflare-api-token -n traefik-private --ignore-not-found=true || true

# Clean up any remaining Ingress resources
echo "--- Cleaning up remaining Ingress resources ---"
for ns in traefik-public traefik-private; do
  if kubectl get namespace "$ns" &>/dev/null; then
    kubectl delete ingress --all -n "$ns" --ignore-not-found=true || true
  fi
done

# Clean up any remaining Certificates
echo "--- Cleaning up remaining Certificates ---"
for ns in traefik-public traefik-private; do
  if kubectl get namespace "$ns" &>/dev/null; then
    kubectl delete certificate --all -n "$ns" --ignore-not-found=true || true
  fi
done

echo "=== Cleanup complete ==="
echo ""
echo "Remaining namespaces:"
kubectl get namespaces

echo ""
echo "Remaining Helm releases:"
helm list --all-namespaces

