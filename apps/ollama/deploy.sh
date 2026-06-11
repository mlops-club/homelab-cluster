#!/bin/bash
# Idempotent deploy for Ollama (GPU-backed inference service).
#   - Creates the namespace + hostPath PVs/PVC for the model store
#   - helm upgrade --installs the otwld/ollama chart with values.yaml
#
# Re-running this script is safe: kubectl apply and helm upgrade --install
# both converge to the desired state.

set -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OLLAMA_CHART_VERSION="1.60.0"

helm repo add otwld https://otwld.github.io/ollama-helm/ >/dev/null
helm repo update otwld >/dev/null

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"

helm upgrade --install ollama otwld/ollama \
    --version "${OLLAMA_CHART_VERSION}" \
    --namespace ollama \
    --values "${SCRIPT_DIR}/values.yaml" \
    --wait \
    --timeout 15m
