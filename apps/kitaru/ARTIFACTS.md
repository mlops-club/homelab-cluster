# Kitaru artifact storage

Operator runbook for Kitaru's artifact store. tl;dr: artifacts (chat transcripts, tool-call payloads, runtime logs) live in **MinIO** at `s3://kitaru-artifacts`, which is backed by **NFS** on the homelab NAS.

## Why not the chart's default local artifact store

The Kitaru Helm chart provisions a single PVC (`kitaru-server-config`) that backs both the SQLite metadata DB and the default ZenML `local` artifact store. That works for a fresh `kitaru deploy` smoke test, but the Kitaru UI breaks the moment you click "View logs" on an execution:

```
Failed to load logs — Files in a local artifact store cannot be accessed from the server.
```

This is **not** a bug — it's an explicit guard in [`zenml/artifact_stores/base_artifact_store.py::_validate_path`](https://github.com/zenml-io/zenml/blob/main/src/zenml/artifact_stores/base_artifact_store.py). ZenML refuses to serve any artifact whose path doesn't start with one of the prefixes in `zenml.constants.REMOTE_FS_PREFIX` (`s3://`, `gs://`, `az://`, `abfs://`, `hdfs://`). The rationale: in a real cluster, the artifact's filesystem only exists on the client that ran the pipeline; the server pod has no way to reach it.

We thought about side-stepping the check by:

- **Pointing the `local` flavor's `path` at a shared NFS PVC mounted on both the agent and the server pod.** The data would be reachable, but the check is path-prefix-driven, not reachability-driven — it would still raise. Confirmed by reading the source.
- **Storing artifacts in a sidecar service the server could `GET` over HTTP.** Equivalent to MinIO with more moving parts.

So we deploy MinIO. ZenML and Kitaru already ship `s3fs` and `boto3` in their server image; the `s3` flavor of artifact store works out of the box with any S3-compatible endpoint (via `client_kwargs.endpoint_url`).

## Topology

```
       ┌───────────────────────── Tailnet ──────────────────────────┐
       │                                                            │
       │     operator's laptop                                      │
       │          │                                                 │
       │          ▼                                                 │
       │   kitaru CLI ── HTTPS ─► kitaru.priv.mlops-club.org        │
       │                                │                           │
       └────────────────────────────────┼───────────────────────────┘
                                        │
                            cluster-internal traffic
                                        │
        ┌───────────────┬───────────────┴───────────────┐
        ▼               ▼                               ▼
  ┌──────────┐   ┌──────────────┐                 ┌──────────────┐
  │  kitaru- │   │ loseit-agent │                 │   future     │
  │  server  │   │              │                 │   clients    │
  └────┬─────┘   └──────┬───────┘                 └──────┬───────┘
       │ s3 GET         │ s3 PUT/GET                    │ s3 PUT/GET
       └──────┬─────────┴────────────┬──────────────────┘
              ▼                      ▼
       ┌────────────────────────────────┐
       │ MinIO  (minio.minio.svc:9000)  │
       │   bucket: kitaru-artifacts     │
       └──────────────┬─────────────────┘
                      │
                      ▼
       ┌────────────────────────────────┐
       │ NAS  (100.117.142.58, NFSv3)   │
       │   /volume1/k8s-homelab/        │
       │   minio-data/                  │
       │     buckets/kitaru-artifacts/  │
       └────────────────────────────────┘
```

## Stack model

Kitaru/ZenML organize stack components by name. Our cluster ships two stacks:

| Stack | Orchestrator | Artifact store | Deployer | Default? |
|---|---|---|---|---|
| `default` | `default` (local) | `default` (local) | `default` (local) | Was active pre-fix |
| `default-s3` | `default` (local) | **`minio` (s3)** | `default` (local) | Active now |

We keep the original `default` stack around so old executions (which reference its components by UUID) still resolve, even though their log fetch will still fail. New flows always run on `default-s3`.

## Bootstrap (one-time per cluster)

```bash
# 1. Deploy MinIO (creates ns, NFS PV, Deployment, Service, root creds, bucket)
bash apps/minio/deploy.sh

# 2. Log in to Kitaru if you haven't already
uvx --from "kitaru[local]" kitaru login https://kitaru.priv.mlops-club.org

# 3. Register the s3 artifact store, create + activate `default-s3`, restart pods
bash apps/kitaru/ops/register-artifact-store.sh
```

After step 3:

- ZenML secret `minio-creds` exists in Kitaru (keys: `aws_access_key_id`, `aws_secret_access_key`).
- Artifact store `minio` (flavor `s3`, path `s3://kitaru-artifacts`, `client_kwargs.endpoint_url = http://minio.minio.svc.cluster.local:9000`) is registered.
- Stack `default-s3` exists and is the **active** stack for the current Kitaru user.
- `kitaru-server` and `loseit-agent` have been bounced so they pick up the new active stack.

## Rotate the MinIO root credentials

1. Generate a new password on the NAS / your shell:
   ```bash
   NEW="$(openssl rand -hex 16)"
   ```
2. Update both Kubernetes Secrets:
   ```bash
   kubectl -n minio create secret generic minio-root \
       --from-literal=rootUser="$(kubectl -n minio get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)" \
       --from-literal=rootPassword="${NEW}" \
       --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n minio rollout restart deploy/minio
   ```
3. Update the ZenML secret in Kitaru:
   ```bash
   bash apps/kitaru/ops/register-artifact-store.sh   # idempotent — re-asserts everything
   ```

## Reverting the stack

If you ever need to fall back to the local artifact store (e.g. for debugging),
flip the active stack:

```bash
uvx --from "kitaru[local]" kitaru stack use default
kubectl -n kitaru rollout restart deploy/kitaru-server
kubectl -n loseit-agent rollout restart deploy/loseit-agent
```

Log fetches will start failing again — that's the original bug; the stack is here only as an escape hatch.

## Known limitations

- **Existing executions don't get retroactive S3 storage.** Runs that completed under the `default` stack still reference the local artifact store; their logs are forever unreachable from the server. Acceptable for the test data we have right now.
- **Single-replica MinIO.** Restarts cause ~5 s of API downtime. Fine for a homelab.
- **Bucket is not versioned.** ZenML writes each artifact to a unique path so we don't need versioning; if you want object-level history, enable it on the bucket via `mc version enable local/kitaru-artifacts`.
- **MinIO has no Ingress.** Console access is via `kubectl port-forward`. This is intentional — the bucket contains chat transcripts that include Lose It! data, which must stay on the Tailnet.

## Physical data layout on the NAS

MinIO uses its filesystem backend (single-node mode), which lays buckets out under the data root with one top-level directory per bucket:

```
/volume1/k8s-homelab/minio-data/
├── .minio.sys/         # MinIO internal state (xl.meta sidecars, usage cache) — don't touch
└── kitaru-artifacts/
    ├── custom_artifacts/      # tool-call payloads, transcripts, summaries
    ├── external_artifacts/    # inputs the flow received
    ├── logs/                  # per-step stdout/stderr text logs
    └── <step-name>/output/    # one subtree per Kitaru step that emits a typed artifact
```

The on-disk layout under the bucket mirrors the prior `~/.config/kitaru/local_stores/<uuid>/` layout we used to see in the agent pod, which is convenient if you ever need to recover artifacts manually from the NAS.
