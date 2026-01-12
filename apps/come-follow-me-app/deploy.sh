#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

: "${CFM_APP_VERSION:?Set CFM_APP_VERSION in .env}"
: "${CFM_APP_GOOGLE_CREDENTIALS_PATH:?Set CFM_APP_GOOGLE_CREDENTIALS_PATH in .env}"
: "${CFM_APP_SPREADSHEET_ID:?Set CFM_APP_SPREADSHEET_ID in .env}"
: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"

if [ ! -f "${CFM_APP_GOOGLE_CREDENTIALS_PATH}" ]; then
  echo "Error: Google credentials file not found at ${CFM_APP_GOOGLE_CREDENTIALS_PATH}"
  exit 1
fi

kubectl create namespace come-follow-me-app --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic google-credentials \
  --from-file=google-credentials.json="${CFM_APP_GOOGLE_CREDENTIALS_PATH}" \
  --namespace come-follow-me-app \
  --dry-run=client -o yaml | kubectl apply -f -

# Create Harbor registry pull secret
kubectl create secret docker-registry harbor-creds \
  --docker-server=cr.priv.mlops-club.org \
  --docker-username=admin \
  --docker-password="${HARBOR_ADMIN_PASSWORD}" \
  --namespace come-follow-me-app \
  --dry-run=client -o yaml | kubectl apply -f -

# Substitute environment variables in manifest and apply
export CFM_APP_VERSION
export CFM_APP_SPREADSHEET_ID
envsubst < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -

