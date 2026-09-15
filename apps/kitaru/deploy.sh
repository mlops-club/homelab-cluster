#!/bin/bash
# Idempotent deploy for Kitaru (ZenML's open-source durable-execution layer
# for AI agents).
#   - Creates the namespace + private Ingress (kitaru.priv.mlops-club.org)
#   - helm upgrade --installs the official Kitaru chart from the public ECR
#     OCI registry, using values.yaml
#
# Re-running this script is safe: kubectl apply and helm upgrade --install
# both converge to the desired state.

set -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KITARU_CHART_VERSION="0.2.0"

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"

helm upgrade --install kitaru-server oci://public.ecr.aws/zenml/kitaru \
    --version "${KITARU_CHART_VERSION}" \
    --namespace kitaru \
    --values "${SCRIPT_DIR}/values.yaml" \
    --wait \
    --timeout 10m
