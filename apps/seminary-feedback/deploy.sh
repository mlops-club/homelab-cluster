#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

: "${SEMINARY_APP_VERSION:?Set SEMINARY_APP_VERSION in .env}"
: "${SEMINARY_GOOGLE_CREDENTIALS_PATH:?Set SEMINARY_GOOGLE_CREDENTIALS_PATH in .env}"
: "${SEMINARY_SPREADSHEET_ID:?Set SEMINARY_SPREADSHEET_ID in .env}"
: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"

if [ ! -f "${SEMINARY_GOOGLE_CREDENTIALS_PATH}" ]; then
  echo "Error: Google credentials file not found at ${SEMINARY_GOOGLE_CREDENTIALS_PATH}"
  exit 1
fi

kubectl create namespace seminary-feedback --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic google-credentials \
  --from-file=google-credentials.json="${SEMINARY_GOOGLE_CREDENTIALS_PATH}" \
  --namespace seminary-feedback \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry harbor-creds \
  --docker-server=cr.priv.mlops-club.org \
  --docker-username=admin \
  --docker-password="${HARBOR_ADMIN_PASSWORD}" \
  --namespace seminary-feedback \
  --dry-run=client -o yaml | kubectl apply -f -

export SEMINARY_APP_VERSION
export SEMINARY_SPREADSHEET_ID
envsubst < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -
