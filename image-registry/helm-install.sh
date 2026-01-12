#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${PROJECT_ROOT}/.env"

: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"
: "${HARBOR_SECRET_KEY:?Set HARBOR_SECRET_KEY in .env}"

kubectl create namespace image-registry --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic harbor-admin \
  --from-literal=HARBOR_ADMIN_PASSWORD="${HARBOR_ADMIN_PASSWORD}" \
  --from-literal=HARBOR_SECRET_KEY="${HARBOR_SECRET_KEY}" \
  --namespace image-registry \
  --dry-run=client -o yaml | kubectl apply -f -

helm repo add harbor https://helm.goharbor.io
helm repo update

helm upgrade --install harbor harbor/harbor \
  --namespace image-registry \
  --values "${SCRIPT_DIR}/values.yaml" \
  --set-string harborAdminPassword="${HARBOR_ADMIN_PASSWORD}" \
  --set-string secretKey="${HARBOR_SECRET_KEY}" \
  --wait
