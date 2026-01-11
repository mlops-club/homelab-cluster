#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

# Add Traefik Helm repository
helm repo add traefik https://helm.traefik.io/traefik
helm repo update

# Install Traefik in traefik-private namespace
# Configure it to be exposed via Tailscale LoadBalancer with External-DNS registration
helm upgrade --install traefik-private traefik/traefik \
  --namespace traefik-private \
  --values "${SCRIPT_DIR}/values.yaml" \
  --wait

