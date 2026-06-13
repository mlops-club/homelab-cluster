# MinIO

Single-replica, NFS-backed, S3-compatible object store. Deployed to the `minio` namespace, reachable **only** in-cluster at `minio.minio.svc.cluster.local:9000`. No Ingress, no public exposure — the bucket holds Kitaru execution artifacts (chat transcripts, tool-call payloads, log files) which must never leave the Tailnet.

## Why it exists

The Kitaru UI refused to render execution logs with the error

> Failed to load logs — Files in a local artifact store cannot be accessed from the server.

ZenML's [`base_artifact_store._validate_path`](https://github.com/zenml-io/zenml/blob/main/src/zenml/artifact_stores/base_artifact_store.py) refuses to serve any artifact path that doesn't start with `s3://`, `gs://`, `az://`, `abfs://`, or `hdfs://` (see `zenml/utils/io_utils.py::is_remote` + `zenml/constants.py::REMOTE_FS_PREFIX`). That check is hardcoded by prefix, so resizing the local PVC or pointing it at NFS does **not** bypass it. The fix is an actual object store — MinIO is the canonical, self-hosted, S3-compatible fit and integrates cleanly with the Kitaru `s3` artifact-store flavor.

## What's deployed

| Resource | Source | Notes |
|---|---|---|
| Namespace `minio` | `manifest.yaml` | |
| Secret `minio-root` | created by `deploy.sh` on first install | Keys: `rootUser`, `rootPassword`. NOT rotated on re-deploys. |
| PV `minio-data` | `manifest.yaml` | Static NFS PV on `100.117.142.58:/volume1/k8s-homelab/minio-data` (pattern matches `apps/audiobookshelf`). 100 Gi, RWO, Retain. |
| PVC `data` | `manifest.yaml` | Binds to `minio-data`. |
| Deployment `minio` | `manifest.yaml` | `quay.io/minio/minio:RELEASE.2024-12-18T13-15-44Z`, single replica, `Recreate` strategy (PVC is RWO). |
| Service `minio` | `manifest.yaml` | ClusterIP, ports 9000 (S3 API) + 9001 (console). |
| Bucket `kitaru-artifacts` | created by `deploy.sh` via a one-shot `mc` Job | Idempotent; safe to re-run. |

## Architecture

```
loseit-agent ──s3 PUT──┐
                       │
                       ▼
                  ┌─────────┐         ┌────────────────────┐
                  │  MinIO  │ ──────► │ NFS (homelab NAS)  │
                  │  :9000  │         │ /volume1/k8s-...   │
                  └─────────┘         │ /minio-data/       │
                       ▲              └────────────────────┘
                       │
kitaru-server ──s3 GET─┘
```

Both the Kitaru server (which serves `/api/v1/.../logs` for the UI) and any client (the agent, the operator's `kitaru` CLI) reach MinIO at the same internal address. The data physically lands on the NAS, so it survives node loss.

## Deploy

```bash
./apps/minio/deploy.sh
```

Idempotent — first run generates 32-char-hex root credentials and stores them in the `minio-root` Secret. Subsequent runs preserve the existing Secret (rotating these would break the artifact-store config in Kitaru that references them).

## Verify

```bash
kubectl -n minio get pods,svc,pvc
kubectl -n minio wait --for=condition=available deploy/minio --timeout=120s

# Confirm the bucket exists (use the MinIO Client via one-shot Job):
kubectl -n minio run mc-ls --rm -it --restart=Never \
    --image=quay.io/minio/mc:RELEASE.2024-11-21T17-21-54Z \
    --overrides='{"spec":{"containers":[{"name":"mc","image":"quay.io/minio/mc:RELEASE.2024-11-21T17-21-54Z","env":[{"name":"U","valueFrom":{"secretKeyRef":{"name":"minio-root","key":"rootUser"}}},{"name":"P","valueFrom":{"secretKeyRef":{"name":"minio-root","key":"rootPassword"}}}],"command":["sh","-c","mc alias set local http://minio.minio.svc.cluster.local:9000 $U $P && mc ls local/"]}]}}'
```

Console UI (admin only — port-forward, do NOT expose):

```bash
kubectl -n minio port-forward svc/minio 9001:9001
# then visit http://localhost:9001 — user = $(kubectl -n minio get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)
```

## How Kitaru is wired to it

After MinIO is up, run:

```bash
bash apps/kitaru/ops/register-artifact-store.sh
```

That script:
1. Reads the MinIO root credentials out of the K8s `minio-root` Secret.
2. Creates a ZenML secret `minio-creds` (in Kitaru's secret store) with those creds.
3. Registers an `s3`-flavor artifact store named `minio` pointing at `s3://kitaru-artifacts` via the MinIO endpoint, with `key`/`secret` sourced from the ZenML secret.
4. Creates a new stack `default-s3` (= the existing local orchestrator + log_store + deployer + the new `minio` artifact store) and activates it.

See [`apps/kitaru/ARTIFACTS.md`](../kitaru/ARTIFACTS.md) for the full operator runbook.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| PVC `data` stuck `Pending` | NAS dir `/volume1/k8s-homelab/minio-data` doesn't exist. Run `apps/minio/deploy.sh` once after pre-creating the dir on the NAS (deploy.sh does NOT create the NAS dir for you — that's done out-of-band via any PVC mount that includes `mkdir -p /mnt/minio-data`). |
| MinIO pod CrashLoop with permission errors on /data | NFS `root_squash` is on. See `storage/README.md` — the cluster-wide fix is `no_root_squash`; if you can't set that, change `runAsUser/fsGroup` to UID 65534 (the squashed user). |
| Bucket-create Job fails with TLS/auth error | Verify `kubectl -n minio get secret minio-root -o yaml` has populated `rootUser` and `rootPassword`. |
| Kitaru UI still says "local artifact store" | `default-s3` stack isn't active — `uvx --from "kitaru[local]" kitaru stack current` should show `default-s3`. If not, run `kitaru stack use default-s3`. |
