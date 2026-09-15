# Kitaru

[Kitaru](https://github.com/zenml-io/kitaru) is ZenML's open-source durable-execution layer for AI agents — it makes agent runs persistent, replayable, and observable, and ships a web UI for browsing executions. Deployed in the `kitaru` namespace, reachable in-cluster at `http://kitaru-server.kitaru.svc.cluster.local:80` and from any Tailnet device at `https://kitaru.priv.mlops-club.org` (private Ingress via `traefik-private`, wildcard TLS from the reflector-replicated `priv-wildcard-tls` secret — no public exposure).

The Kitaru Deployment, Service, ServiceAccount, and SQLite PVC are Helm-managed by `deploy.sh` (the official chart at `oci://public.ecr.aws/zenml/kitaru`); the repo only tracks the Namespace and the Ingress in `manifest.yaml`. Apply infra changes (including the Ingress) with `kubectl apply -f apps/kitaru/manifest.yaml`.

## What's deployed

| Resource | Source | Notes |
|---|---|---|
| Namespace `kitaru` | `manifest.yaml` | |
| Ingress `kitaru` | `manifest.yaml` | `traefik-private`, host `kitaru.priv.mlops-club.org`, TLS from reflected `priv-wildcard-tls` |
| Deployment `kitaru-server` | Helm chart `kitaru` 0.2.0 | Image `zenmldocker/kitaru:0.94.1` (Kitaru UI layered on the ZenML server) |
| Service `kitaru-server` | Helm chart | ClusterIP, port 80 → container 8080 |
| PVC `kitaru-server-config` | Helm chart | 20Gi on `local-path` (k3s default) for SQLite + artifact metadata |

### Why this image

The Kitaru repo ships **two** server-side container images:

- `zenmldocker/zenml-server` — the plain ZenML metadata server, no Kitaru UI.
- `zenmldocker/kitaru` — same ZenML server, with the Kitaru Python package installed on top and the ZenML dashboard replaced by the Kitaru UI. Built from [`docker/Dockerfile`](https://github.com/zenml-io/kitaru/blob/develop/docker/Dockerfile) in the Kitaru repo.

The official Kitaru Helm chart wraps the ZenML chart and pulls `zenmldocker/kitaru` by default, so we don't have to build anything. This is the path the chart's README recommends and what we use here.

## Deploy

```bash
./apps/kitaru/deploy.sh
```

Idempotent — `kubectl apply` and `helm upgrade --install` both converge to whatever's in `manifest.yaml` and `values.yaml`. First boot takes 30-60s for the image pull and SQLite migrations.

## Verify

```bash
kubectl -n kitaru get pods
kubectl -n kitaru wait --for=condition=available deploy/kitaru-server --timeout=300s
kubectl -n kitaru get ingress
kubectl -n kitaru logs deploy/kitaru-server | tail
```

End-to-end from a Tailnet device:

```bash
curl -sSf -o /dev/null -w "%{http_code}\n" https://kitaru.priv.mlops-club.org/
curl -sS https://kitaru.priv.mlops-club.org/health
```

The web UI lives at `https://kitaru.priv.mlops-club.org/` — login uses the OAuth2 password-bearer scheme (default user `default`, no password) on first boot; create real users via the Kitaru CLI afterwards.

CLI side (operator's laptop on the Tailnet):

```bash
pipx install kitaru
kitaru login https://kitaru.priv.mlops-club.org
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Pod `Pending` with PVC `kitaru-server-config` unbound | `local-path` provisioner isn't running. `kubectl -n kube-system get pods | grep local-path`. |
| `kitaru.priv.mlops-club.org` doesn't resolve | Not on the Tailnet, OR external-dns hasn't created the record yet (`kubectl -n traefik-private logs deploy/external-dns`). |
| TLS handshake fails on `kitaru.priv.mlops-club.org` | The `priv-wildcard-tls` Secret hasn't been mirrored into the `kitaru` namespace yet — check reflector is running: `kubectl -n traefik-private get deploy reflector`. |
| `502 Bad Gateway` from Traefik | Pod isn't ready yet, or the Service targets the wrong port. `kubectl -n kitaru describe svc kitaru-server` should show `targetPort: 8080`. |
| Pod restarts with SQLite migration errors | Delete the PVC and re-deploy — only safe on a fresh install: `kubectl -n kitaru delete pvc kitaru-server-config`. |
| `helm upgrade` fails pulling the chart | The chart lives in an OCI registry (`public.ecr.aws/zenml/kitaru`); helm 3.8+ required and the host needs egress to ECR. |
| UI shows "Failed to load logs — Files in a local artifact store cannot be accessed from the server." on an execution detail page | The execution ran on the old `default` stack with the local artifact store. New executions on the `default-s3` stack (MinIO-backed) load fine. See [`ARTIFACTS.md`](ARTIFACTS.md) for the storage model and migration runbook. |

## Artifact storage

Kitaru artifacts and per-step runtime logs live in **MinIO** (`apps/minio/`), backed by NFS on the homelab NAS. The active stack is `default-s3`, which pairs the chart's local orchestrator/deployer with an `s3`-flavor artifact store named `minio` pointing at `s3://kitaru-artifacts` via `http://minio.minio.svc.cluster.local:9000`. See [`ARTIFACTS.md`](ARTIFACTS.md) for the full operator runbook (bootstrap, rotate, revert).
