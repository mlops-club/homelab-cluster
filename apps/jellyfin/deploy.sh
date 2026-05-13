#!/bin/bash -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create NAS directories via a temporary PV/PVC + Job (CSI driver requires Persistent mode)
kubectl apply -f "${SCRIPT_DIR}/init-nas.yaml"
kubectl wait --for=condition=complete job/mkdir-videos --timeout=120s
kubectl delete job/mkdir-videos pvc/nfs-root-tmp pv/nfs-root-tmp

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"
