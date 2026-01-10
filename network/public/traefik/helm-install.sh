#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

# Create the traefik-public namespace
kubectl create namespace traefik-public --dry-run=client -o yaml | kubectl apply -f -

# Add Traefik Helm repository
helm repo add traefik https://helm.traefik.io/traefik
helm repo update

# Install Traefik in traefik-public namespace
# Configure it as ClusterIP service (Cloudflare Tunnel will handle external access)
helm upgrade --install traefik-public traefik/traefik \
  --namespace traefik-public \
  --values "${SCRIPT_DIR}/values.yaml" \
  --wait

# Expose Traefik itself at traefik.mlops-club.org via Cloudflare Tunnel
kubectl apply -f "${SCRIPT_DIR}/traefik-ingress.yaml"

