#!/bin/bash
# deploy.sh
# Purpose: Deploy the personal-finance FIRE planner to the K3s cluster
# Scope: NAS directory, Secrets, and all resources in manifest.yaml for the personal-finance namespace
# Overview: Creates the users/ directory on the NAS, the Harbor pull secret, and (once) a random
#     session-signing key, then applies manifest.yaml with the image tag substituted. Safe to re-run:
#     the NAS mkdir is idempotent and an existing session-secret is kept, so sign-ins stay valid.
# Dependencies: kubectl, envsubst, openssl, a .env at the repo root (see env.example)
# Usage: ./apps/personal-finance/deploy.sh
# Related: manifest.yaml, init-nas.yaml, README.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

: "${PERSONAL_FINANCE_APP_VERSION:?Set PERSONAL_FINANCE_APP_VERSION in .env}"
: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"

# Create the users/ directory on the NAS via a temporary PV/PVC + Job (CSI driver requires Persistent mode)
kubectl apply -f "${SCRIPT_DIR}/init-nas.yaml"
kubectl wait --for=condition=complete job/mkdir-personal-finance --timeout=120s
kubectl delete job/mkdir-personal-finance pvc/nfs-root-tmp pv/nfs-root-tmp

kubectl create namespace personal-finance --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry harbor-creds \
  --docker-server=cr.priv.mlops-club.org \
  --docker-username=admin \
  --docker-password="${HARBOR_ADMIN_PASSWORD}" \
  --namespace personal-finance \
  --dry-run=client -o yaml | kubectl apply -f -

# Session-signing key: generated once and never overwritten, so sign-ins survive redeploys
if ! kubectl get secret session-secret --namespace personal-finance >/dev/null 2>&1; then
  kubectl create secret generic session-secret \
    --from-literal=session_secret="$(openssl rand -hex 32)" \
    --namespace personal-finance
fi

export PERSONAL_FINANCE_APP_VERSION
envsubst '${PERSONAL_FINANCE_APP_VERSION}' < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -

kubectl rollout status deployment/personal-finance --namespace personal-finance --timeout=180s
