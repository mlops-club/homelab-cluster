#!/bin/bash -euox pipefail
# deploy.sh
# Purpose: Deploy Immich (self-hosted Google Photos) to the K3s cluster
# Usage: ./apps/immich/deploy.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create NAS directories via a temporary PV/PVC + Job (CSI driver requires Persistent mode)
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-root-tmp-immich
spec:
  capacity:
    storage: 1Gi
  accessModes: [ReadWriteMany]
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: nfs-root-tmp-immich
    volumeAttributes:
      server: "100.117.142.58"
      share: "/volume1/k8s-homelab"
  mountOptions: [nfsvers=3, nolock]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nfs-root-tmp-immich
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  volumeName: nfs-root-tmp-immich
  resources:
    requests:
      storage: 1Gi
---
apiVersion: batch/v1
kind: Job
metadata:
  name: mkdir-immich
spec:
  ttlSecondsAfterFinished: 30
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: mk
        image: busybox
        command: ["sh", "-c", "mkdir -p /mnt/media/photos"]
        volumeMounts:
        - name: nfs
          mountPath: /mnt
      volumes:
      - name: nfs
        persistentVolumeClaim:
          claimName: nfs-root-tmp-immich
EOF

kubectl wait --for=condition=complete job/mkdir-immich --timeout=120s
kubectl delete job/mkdir-immich pvc/nfs-root-tmp-immich pv/nfs-root-tmp-immich

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"
