#!/bin/bash
# Build → push → deploy the loseit-agent service.
#
# Idempotent. Re-running it converges the cluster to whatever's in
# manifest.yaml + server.py at the current commit. The agent-token Secret
# is created on first deploy and NOT rotated afterwards — rotating it would
# break the Pipe config we land in S3.
#
# Required: ../../.env contains `HARBOR_ADMIN_PASSWORD=...`.
#           IMAGE_TAG can be overridden via env; default is `<git-short-sha>`
#           with a `-dirty` suffix if the working tree has uncommitted changes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck disable=SC1091
source "${PROJECT_ROOT}/.env"

: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"

REGISTRY="cr.priv.mlops-club.org"
IMAGE_REPO="${REGISTRY}/loseit-agent/agent"
NAMESPACE="loseit-agent"

# --- compute image tag ----------------------------------------------------
if [[ -z "${IMAGE_TAG:-}" ]]; then
  SHA="$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD)"
  if ! git -C "${PROJECT_ROOT}" diff --quiet || ! git -C "${PROJECT_ROOT}" diff --cached --quiet; then
    IMAGE_TAG="${SHA}-dirty"
  else
    IMAGE_TAG="${SHA}"
  fi
fi
export IMAGE_TAG
echo ">>> deploying loseit-agent image tag: ${IMAGE_TAG}"

# --- build + push ---------------------------------------------------------
echo ">>> docker login ${REGISTRY}"
echo "${HARBOR_ADMIN_PASSWORD}" | docker login "${REGISTRY}" -u admin --password-stdin

echo ">>> docker build ${IMAGE_REPO}:${IMAGE_TAG}"
docker build \
  --platform linux/amd64 \
  -t "${IMAGE_REPO}:${IMAGE_TAG}" \
  "${SCRIPT_DIR}"

echo ">>> docker push ${IMAGE_REPO}:${IMAGE_TAG}"
docker push "${IMAGE_REPO}:${IMAGE_TAG}"

# --- ensure namespace + Harbor pull secret --------------------------------
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry harbor-creds \
  --docker-server="${REGISTRY}" \
  --docker-username=admin \
  --docker-password="${HARBOR_ADMIN_PASSWORD}" \
  --namespace "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

# --- ensure agent-token Secret (create-once; do NOT rotate) ---------------
if kubectl -n "${NAMESPACE}" get secret agent-token >/dev/null 2>&1; then
  echo ">>> agent-token secret already exists; keeping it (no rotation)"
else
  echo ">>> creating agent-token secret (first deploy)"
  TOKEN="$(openssl rand -hex 32)"
  kubectl create secret generic agent-token \
    --from-literal=token="${TOKEN}" \
    --namespace "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

# --- apply manifest -------------------------------------------------------
echo ">>> applying manifest with IMAGE_TAG=${IMAGE_TAG}"
envsubst < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -

# Nudge the rollout to pick up the new image even when the tag string didn't
# change (e.g. re-running on a dirty tree).
kubectl -n "${NAMESPACE}" rollout restart deploy/loseit-agent >/dev/null

echo ">>> done. waiting for rollout..."
kubectl -n "${NAMESPACE}" rollout status deploy/loseit-agent --timeout=180s
