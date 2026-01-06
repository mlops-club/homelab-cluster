#!/bin/bash -euox pipefail

# internal services (tailscale) with pretty DNS (cloudflare A records):
# create cloudflare API token secret if it doesn't exist

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

# create cloudflare API token secret if it doesn't exist
kubectl create secret generic cloudflare-api-token \
  --from-literal=cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  --namespace traefik-private \
  --dry-run=client -o yaml | kubectl apply -f -

helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
helm repo update

helm upgrade --install external-dns external-dns/external-dns \
  --namespace traefik-private \
  --values "${SCRIPT_DIR}/values.yaml" \
  --set "env[0].name=CF_API_TOKEN" \
  --set "env[0].valueFrom.secretKeyRef.name=cloudflare-api-token" \
  --set "env[0].valueFrom.secretKeyRef.key=cloudflare_api_token" \
  --set "cloudflare.zoneIdFilter=${CLOUDFLARE_ZONE_ID}" \
  --set "domainFilters[0]=priv.${CLOUDFLARE_DOMAIN}" \
  --wait --timeout 30s

