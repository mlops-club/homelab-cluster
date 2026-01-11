#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

# Add Traefik Helm repository
helm repo add traefik https://helm.traefik.io/traefik
helm repo update

# Install Traefik in traefik-public namespace
# Configure it as ClusterIP service (Cloudflare Tunnel will handle external access)
helm upgrade --install traefik-public traefik/traefik \
  --namespace traefik-public \
  --values "${SCRIPT_DIR}/values.yaml" \
  --wait

# Create wildcard certificate for *.mlops-club.org
echo "Creating wildcard certificate for *.mlops-club.org..."
kubectl apply -f "${SCRIPT_DIR}/mlops-wildcard-certificate.yaml"

# Wait for certificate to be ready (with timeout)
echo "Waiting for certificate to be ready..."
if kubectl wait --for=condition=Ready certificate/mlops-wildcard -n traefik-public --timeout=300s 2>/dev/null; then
  echo "Certificate is ready"
else
  echo "Warning: Certificate may take a moment to become ready"
fi

# Expose Traefik itself at traefik.mlops-club.org via Cloudflare Tunnel
kubectl apply -f "${SCRIPT_DIR}/traefik-ingress.yaml"

