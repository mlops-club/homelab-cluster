#!/bin/bash
set -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

: "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"

cd "${SCRIPT_DIR}"

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")
if [[ -n $(git status --porcelain 2>/dev/null) ]]; then GIT_SHA="${GIT_SHA}-dirty"; fi
IMAGE_TAG="${IMAGE_TAG:-v2-${GIT_SHA}}"
export IMAGE_TAG

docker login cr.priv.mlops-club.org -u admin -p "${HARBOR_ADMIN_PASSWORD}"

docker build --platform linux/amd64 \
  -t "cr.priv.mlops-club.org/loseit-agent/agent:${IMAGE_TAG}" .
docker push "cr.priv.mlops-club.org/loseit-agent/agent:${IMAGE_TAG}"

kubectl create namespace loseit-agent --dry-run=client -o yaml | kubectl apply -f -

kubectl -n loseit-agent create secret docker-registry harbor-creds \
  --docker-server=cr.priv.mlops-club.org \
  --docker-username=admin \
  --docker-password="${HARBOR_ADMIN_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

if ! kubectl -n loseit-agent get secret agent-token >/dev/null 2>&1; then
  kubectl -n loseit-agent create secret generic agent-token \
    --from-literal=token="$(openssl rand -hex 32)"
fi

envsubst < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -
kubectl -n loseit-agent rollout restart deploy/loseit-agent
kubectl -n loseit-agent rollout status deploy/loseit-agent --timeout=180s
