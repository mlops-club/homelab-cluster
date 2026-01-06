#!/bin/bash -euox pipefail

# Replicates secrets across namespaces using annotations
# Automatically synchronizes priv-wildcard-tls secret to all namespaces

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

helm repo add emberstack https://emberstack.github.io/helm-charts
helm repo update

helm upgrade --install reflector emberstack/reflector \
  --namespace traefik-private \
  --create-namespace \
  --values "${SCRIPT_DIR}/values.yaml" \
  --wait

