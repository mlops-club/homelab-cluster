#!/bin/bash -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create NAS directories via a temporary PV/PVC + Job (CSI driver requires Persistent mode)
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-root-tmp
spec:
  capacity:
    storage: 1Gi
  accessModes: [ReadWriteMany]
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: nfs-root-tmp
    volumeAttributes:
      server: "100.117.142.58"
      share: "/volume1/k8s-homelab"
  mountOptions: [nfsvers=3, nolock]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nfs-root-tmp
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  volumeName: nfs-root-tmp
  resources:
    requests:
      storage: 1Gi
---
apiVersion: batch/v1
kind: Job
metadata:
  name: mkdir-media
spec:
  ttlSecondsAfterFinished: 30
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: mk
        image: busybox
        command: ["sh", "-c", "mkdir -p /mnt/media/audiobooks /mnt/media/podcasts /mnt/media/ebooks/Books"]
        volumeMounts:
        - name: nfs
          mountPath: /mnt
      volumes:
      - name: nfs
        persistentVolumeClaim:
          claimName: nfs-root-tmp
EOF

kubectl wait --for=condition=complete job/mkdir-media --timeout=120s
kubectl delete job/mkdir-media pvc/nfs-root-tmp pv/nfs-root-tmp

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"
