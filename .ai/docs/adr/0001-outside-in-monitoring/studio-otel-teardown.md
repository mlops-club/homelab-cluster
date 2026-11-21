# Studio OTel POC: teardown

**Purpose**: Remove everything the Studio OpenTelemetry POC created, with exact commands, and prove production
(`golden-rules-studio`) was not touched

**Scope**: Cluster (namespace `golden-rules-studio-otel`), Harbor (one image tag), Grafana Cloud (folder, two
dashboards, one access policy + token), the laptop (credentials file, Podman login, containers, scratch data),
and the three branches

**Related**: [studio-otel-poc.md](studio-otel-poc.md), deploy repo `otel/teardown-otel.sh`,
`monitoring/terraform-studio-otel/`

---

## What exists

| Where | Resource | Created by |
|---|---|---|
| Cluster | Namespace `golden-rules-studio-otel` (label `purpose=studio-otel-poc`) with: Deployments `golden-rules-studio`, `otel-collector`; Services of the same names; Ingress `golden-rules-studio` (`studio-otel.priv.mlops-club.org`); ConfigMap `otel-collector`; ServiceAccount, Role, RoleBinding `otel-collector`; Secrets `harbor-creds`, `studio-password`, `grafana-otlp`; PVC `studio-data` | `otel/setup-otel.sh`, `otel/deploy-otel.sh` |
| Cluster | PV `pvc-2adad8b0-…` (local-path, reclaim **Delete**: removed with the PVC) | the PVC |
| Cluster | Secrets `priv-wildcard-tls`, `mlops-wildcard-tls` in the namespace | reflector (copies; go with the namespace) |
| Harbor | `cr.priv.mlops-club.org/golden-rules-studio/app:6308326-otel` | `otel/build-otel.sh` + in-cluster `crane push` |
| Grafana Cloud | Folder `studio-otel-poc`; dashboards `studio-otel-pages`, `studio-otel-trace` | `monitoring/terraform-studio-otel` (own state) |
| Grafana Cloud | Access policy `studio-otel-poc` + token `studio-otel-collector` (expires 2026-12-21) | `monitoring/terraform-studio-otel/otlp-token.sh create` |
| Grafana Cloud | ~1 week of POC spans in Tempo | the POC; expire with the 14-day retention (cannot be deleted) |
| Laptop | `~/credentials/homelab-otel.env` (chmod 600) | `setup-otel.sh`, `otlp-token.sh` |
| Laptop | Podman login to `cr.priv.mlops-club.org`; image `…/app:6308326-otel`; container `studio-otel-local`; image `otel/opentelemetry-collector-contrib:0.165.0` | the POC |
| Laptop | Scratch seed copy (~560 MB) and local test servers | the POC (session scratch folder) |
| GitHub | Branches: ctdl-xtra `feat/otel-instrumentation-poc`, deploy repo `feat/otel-instrumentation-poc`, homelab-cluster `feat/studio-otel-poc` | the POC |

**Not created by the POC, leave alone**: ClusterRole/ClusterRoleBinding `otel-collector` (they belong to the
older `opentelemetry` namespace collector, created 2026-06-13). No cluster-scoped object was created; the POC's
collector uses a namespaced Role.

## Steps

### 0. Production baseline

```bash
kubectl -n golden-rules-studio get pods \
  -o custom-columns='POD:.metadata.name,STARTED:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.spec.containers[0].image' \
  | tee /tmp/prod-before.txt
curl -s -o /dev/null -w '%{http_code}\n' https://golden-rules-studio.mlops-club.org/api/health   # 200
```

### 1. Cluster (deploy repo)

```bash
cd golden-rules-studio-deploy   # branch feat/otel-instrumentation-poc
./otel/teardown-otel.sh         # prints prod before/after; deletes the namespace (and so the PVC → PV)
```

Equivalent by hand: `kubectl delete namespace golden-rules-studio-otel --wait`.

### 2. Harbor image tag

Harbor UI → project `golden-rules-studio` → repository `app` → tag `6308326-otel` → Delete; or with an account
that may delete artifacts:

```bash
HARBOR_USER=… HARBOR_PASSWORD=… ./otel/teardown-otel.sh --images   # deletes every *-otel tag
```

Production tags (`<sha>` without `-otel`) are not matched.

### 3. Grafana Cloud (homelab repo)

```bash
cd monitoring/terraform-studio-otel
./tf destroy                    # folder + 2 dashboards; this root's own state only
./otlp-token.sh revoke          # token studio-otel-collector, then policy studio-otel-poc
./otlp-token.sh list            # studio-otel-poc no longer listed
```

`monitoring/terraform/` (the main POC root) is not touched.

### 4. Laptop

```bash
rm ~/credentials/homelab-otel.env
podman logout cr.priv.mlops-club.org
podman rm -f studio-otel-local
podman rmi cr.priv.mlops-club.org/golden-rules-studio/app:6308326-otel otel/opentelemetry-collector-contrib:0.165.0
pkill -f 'golden-datasets serve --root .*/seed/root' || true
# the scratch seed lives in the session's scratch folder and goes with it
```

### 5. Branches (only if the POC is abandoned)

```bash
git -C ctdl-xtra push origin --delete feat/otel-instrumentation-poc                    # public repo: no PR was opened
git -C golden-rules-studio-deploy push origin --delete feat/otel-instrumentation-poc
git -C homelab-cluster push origin --delete feat/studio-otel-poc
```

The dashboard's screenshots are served from the homelab branch, so delete it after step 3.

### 6. Verify

```bash
kubectl get namespace golden-rules-studio-otel                 # NotFound
kubectl get pv | grep golden-rules-studio-otel                 # nothing
kubectl -n golden-rules-studio get pods \
  -o custom-columns='POD:.metadata.name,STARTED:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.spec.containers[0].image' \
  | diff /tmp/prod-before.txt - && echo "production unchanged"
curl -s -o /dev/null -w '%{http_code}\n' https://golden-rules-studio.mlops-club.org/api/health   # 200
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
  "$GRAFANA_URL/api/dashboards/uid/studio-otel-pages"                                            # 404
dig +short studio-otel.priv.mlops-club.org   # still resolves (wildcard DNS): expect 404 from Traefik, not the Studio
```

## Checked against the real resources (dry run, 2026-11-21)

| Resource | Removed by | Production object with a similar name? | Safe |
|---|---|---|---|
| Namespace `golden-rules-studio-otel` and everything in it | step 1 | `golden-rules-studio` namespace: a different name; `kubectl delete namespace` takes one exact name | ✅ |
| PV of `studio-data` | step 1 (reclaim Delete) | production uses `emptyDir`, no PV | ✅ |
| ClusterRole `otel-collector` | **not removed** (not ours) | n/a | ✅ |
| Harbor `app:6308326-otel` | step 2 | `app:a78be91` (production) is untouched: the script only matches `-otel` tags | ✅ |
| Grafana folder/dashboards | step 3 (`./tf destroy` in this root) | the main POC root has its own state | ✅ |
| Access policy `studio-otel-poc` | step 3 (by id from the credentials file) | other policies are not touched | ✅ |
| DNS | nothing to remove: `*.priv.mlops-club.org` is a wildcard; no record was added | n/a | ✅ |
| Azure | nothing to remove: the instance had no Azure credentials; the laptop seed only read | production data unchanged | ✅ |
