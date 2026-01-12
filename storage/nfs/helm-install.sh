#!/bin/bash -euox pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${PROJECT_ROOT}/.env"

NFS_SERVER="${NFS_SERVER:-nas}"
NFS_SHARE="${NFS_SHARE:-/home/eric/k8s-homelab/harbor}"
NFS_STORAGE_CLASS_NAME="${NFS_STORAGE_CLASS_NAME:-nas-nfs}"
NFS_NAMESPACE="${NFS_NAMESPACE:-nfs-system}"
NFS_MOUNT_OPTIONS="${NFS_MOUNT_OPTIONS:-nfsvers=4.1}"

helm repo add csi-driver-nfs https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts
helm repo update

kubectl create namespace "${NFS_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
  --namespace "${NFS_NAMESPACE}" \
  --values "${SCRIPT_DIR}/values.yaml" \
  --wait

cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ${NFS_STORAGE_CLASS_NAME}
provisioner: nfs.csi.k8s.io
parameters:
  server: ${NFS_SERVER}
  share: ${NFS_SHARE}
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
mountOptions:
  - ${NFS_MOUNT_OPTIONS}
EOF
