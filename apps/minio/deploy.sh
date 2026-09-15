#!/bin/bash
# Idempotent deploy for MinIO (single-replica, NFS-backed, internal-only).
#
# Order of operations:
#   1. Ensure the `minio` namespace + `minio-root` Secret exist. The Secret
#      is generated on first install (32-byte hex root user + 32-byte hex
#      root password) and left untouched on subsequent runs — rotating
#      credentials would break any client that already trusts them.
#   2. Apply manifest.yaml (namespace is idempotent; the Secret block in
#      manifest.yaml is NOT applied if the live Secret already has real
#      values — we filter it out via kustomize-style streaming).
#   3. Wait for the MinIO Deployment to become Ready.
#   4. Run a one-shot K8s Job that uses `mc` (MinIO Client) to create the
#      `kitaru-artifacts` bucket if it doesn't already exist.
#
# Re-running this script is safe — every step is upsert-style.

set -euox pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BUCKET_NAME="${BUCKET_NAME:-kitaru-artifacts}"

# ---------------------------------------------------------------------------
# 1. Namespace + root Secret
# ---------------------------------------------------------------------------
# Create namespace first so the Secret has somewhere to land.
kubectl get namespace minio >/dev/null 2>&1 || kubectl create namespace minio

# Generate root credentials only on first install. We intentionally do NOT
# rotate them across re-runs — the Kitaru artifact-store registration in
# apps/kitaru/ops/register-artifact-store.sh stores the same access/secret
# keys server-side, and they need to stay in lockstep.
if ! kubectl -n minio get secret minio-root >/dev/null 2>&1; then
    echo "[minio/deploy] Generating MinIO root credentials (first install)."
    ROOT_USER="kitaru-$(openssl rand -hex 6)"
    # MinIO root password must be >=8 chars; 32 hex chars is plenty.
    ROOT_PASSWORD="$(openssl rand -hex 16)"
    kubectl -n minio create secret generic minio-root \
        --from-literal="rootUser=${ROOT_USER}" \
        --from-literal="rootPassword=${ROOT_PASSWORD}"
    unset ROOT_USER ROOT_PASSWORD
fi

# ---------------------------------------------------------------------------
# 2. Apply the rest of the manifest (filtering out the placeholder Secret).
# ---------------------------------------------------------------------------
# yq isn't a hard dependency on every operator's machine; use a python
# one-liner that strips any Secret named "minio-root" from the stream so
# the placeholder block in manifest.yaml never overwrites the real Secret.
python3 - "${SCRIPT_DIR}/manifest.yaml" <<'PY' | kubectl apply -f -
import sys, yaml
docs = list(yaml.safe_load_all(open(sys.argv[1])))
filtered = [
    d for d in docs
    if not (d and d.get("kind") == "Secret" and d.get("metadata", {}).get("name") == "minio-root")
]
print(yaml.safe_dump_all(filtered, sort_keys=False))
PY

# ---------------------------------------------------------------------------
# 3. Wait for MinIO to be ready.
# ---------------------------------------------------------------------------
kubectl -n minio rollout status deploy/minio --timeout=5m

# ---------------------------------------------------------------------------
# 4. Ensure the bucket exists. Use a one-shot Job with `mc` so this stays
#    pure-kubectl and doesn't require the operator to install mc locally.
#    The Job is deleted at the end so subsequent runs don't fail with
#    "Job ... already exists".
# ---------------------------------------------------------------------------
JOB_NAME="minio-create-bucket-$(date +%s)"

cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: minio
spec:
  backoffLimit: 3
  ttlSecondsAfterFinished: 60
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: mc
          image: quay.io/minio/mc:RELEASE.2024-11-21T17-21-54Z
          env:
            - name: ROOT_USER
              valueFrom:
                secretKeyRef:
                  name: minio-root
                  key: rootUser
            - name: ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: minio-root
                  key: rootPassword
            - name: BUCKET
              value: "${BUCKET_NAME}"
          # We use \`mc alias set\` rather than the \`MC_HOST_<alias>\` env-var
          # form because the latter requires double-shell interpolation
          # (\$(ROOT_USER) -> via Kubernetes envvar expansion -> via mc URL
          # parser), and the URL-encoding of any '/' or '+' in the secret
          # value breaks it in subtle ways. \`alias set\` accepts them raw.
          command:
            - /bin/sh
            - -c
            - |
              set -eux
              mc alias set local http://minio.minio.svc.cluster.local:9000 "\$ROOT_USER" "\$ROOT_PASSWORD"
              mc mb --ignore-existing "local/\$BUCKET"
              mc ls local/
EOF

kubectl -n minio wait --for=condition=complete "job/${JOB_NAME}" --timeout=2m
echo "[minio/deploy] Bucket '${BUCKET_NAME}' ensured."

echo ""
echo "MinIO is up at minio.minio.svc.cluster.local:9000 (cluster-internal only)."
echo "Bucket: ${BUCKET_NAME}"
echo ""
echo "Next: bash apps/kitaru/ops/register-artifact-store.sh"
