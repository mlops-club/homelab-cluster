#!/bin/bash
# Purpose: Deploy the in-cluster Synthetic Monitoring probe agent
# Scope: Creates namespace sm-probe, the token Secret (piped from Terraform output, never written to disk)
#   and the agent Deployment
# Usage: apps/sm-probe/deploy.sh   (needs kubectl context on the homelab cluster and monitoring/terraform/tf working)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF="${SCRIPT_DIR}/../../monitoring/terraform/tf"

kubectl create namespace sm-probe --dry-run=client -o yaml | kubectl apply -f -
"${TF}" output -raw cluster_probe_token |
  kubectl create secret generic sm-probe-token -n sm-probe --from-file=api-token=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"
kubectl rollout restart deployment/sm-probe -n sm-probe # pick up a rotated token
kubectl rollout status deployment/sm-probe -n sm-probe --timeout=180s
