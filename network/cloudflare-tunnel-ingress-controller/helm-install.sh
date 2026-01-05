#!/bin/bash -euox pipefail

# external public services with pretty DNS (cloudflare tunnels): 
# creates cloudflare tunnels for ingresses with the right annotations

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

helm repo add strrl.dev https://helm.strrl.dev
helm repo update

helm upgrade --install --wait \
  -n cloudflare-tunnel-ingress-controller --create-namespace \
  cloudflare-tunnel-ingress-controller \
  strrl.dev/cloudflare-tunnel-ingress-controller \
  --values "${SCRIPT_DIR}/values.yaml" \
  --set=cloudflare.apiToken="${CLOUDFLARE_API_TOKEN}" \
  --set=cloudflare.accountId="${CLOUDFLARE_ACCOUNT_ID}" \
  --set=cloudflare.tunnelName="k3s-tunnel"

