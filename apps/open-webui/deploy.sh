#!/bin/bash
# Idempotent deploy for Open WebUI (LLM chat UI in front of Ollama).
#   - Creates the namespace + private Ingress (chat.priv.mlops-club.org)
#   - helm upgrade --installs the open-webui chart with values.yaml
#
# Prerequisite: ./apps/ollama/deploy.sh has already run (Open WebUI's
# values.yaml points at the ollama service in the ollama namespace).

set -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OPEN_WEBUI_CHART_VERSION="14.8.0"

helm repo add open-webui https://helm.openwebui.com/ >/dev/null
helm repo update open-webui >/dev/null

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"

helm upgrade --install open-webui open-webui/open-webui \
    --version "${OPEN_WEBUI_CHART_VERSION}" \
    --namespace open-webui \
    --values "${SCRIPT_DIR}/values.yaml" \
    --wait \
    --timeout 10m
