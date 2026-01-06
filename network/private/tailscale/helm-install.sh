#!/bin/bash -euox pipefail

# internal services (tailscale) with no pretty DNS:
# sets up tailscale networking for a particular service so the service is accessible via a static IP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update

helm upgrade --install tailscale-operator tailscale/tailscale-operator \
  --namespace traefik-private \
  --create-namespace \
  --values "${SCRIPT_DIR}/values.yaml" \
  --set-string oauth.clientId="${TAILSCALE_CLIENT_ID}" \
  --set-string oauth.clientSecret="${TAILSCALE_CLIENT_SECRET}" \
  --wait

