#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/nginx-deployment"

# Remove sample workloads and ingresses
kubectl delete -f "${MANIFEST_DIR}/manifest-internal-tailscale.yaml" --ignore-not-found=true
kubectl delete -f "${MANIFEST_DIR}/manifest-public-cloudflare.yaml" --ignore-not-found=true
kubectl delete -f "${MANIFEST_DIR}/manifest-public-cloudflare-traefik.yaml" --ignore-not-found=true
kubectl delete -f "${MANIFEST_DIR}/manifest-internal-tailscale-traefik.yaml" --ignore-not-found=true
kubectl delete -f "${MANIFEST_DIR}/manifest-internal-https.yaml" --ignore-not-found=true

# Uninstall helm charts installed by install-helm-charts.sh
helm uninstall cloudflare-tunnel-ingress-controller \
  --namespace cloudflare-tunnel-ingress-controller \
  || true
helm uninstall tailscale-operator \
  --namespace tailscale \
  || true
helm uninstall external-dns \
  --namespace kube-system \
  || true

# Clean up supporting secrets created during install
kubectl delete secret cloudflare-api-token \
  --namespace kube-system \
  --ignore-not-found=true

