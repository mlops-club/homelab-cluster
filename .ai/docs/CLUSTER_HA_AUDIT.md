# Cluster High-Availability Audit

**Purpose**: Inventory every service on the cluster and identify single points of failure (SPOFs) that bind a service to one node

**Scope**: All Deployments, StatefulSets, DaemonSets, PersistentVolumes, and the Kubernetes API endpoint on the K3s cluster; the NAS is treated as an accepted SPOF

**Overview**: Classifies each service into one of three tiers: node-bound (down until a specific node
    returns), single-replica (recovers on its own after the node-unreachable eviction delay), or
    already HA. Each row lists the state or deployment choices that prevent HA and a recommendation
    to remove the SPOF. Cross-cutting causes (local-path storage, the unreachable kube-vip address,
    the 300-second eviction delay, StatefulSet behaviour on dead nodes, NFS `nolock`) are described
    once in their own section and referenced from the tables. A measurement section (outside-in
    probes, inside-in probes, heartbeats) comes before the remediation list, because a baseline
    is needed both to prioritize the work and to verify each change.

**Dependencies**: kubectl access to the cluster, `k3s-ansible/inventory/cluster/`, `apps/*/manifest.yaml`

**Exports**: Per-service SPOF findings and HA recommendations, prioritized remediation list

**Related**: `.ai/howto/how-to-troubleshoot-kubernetes.md`, `storage/README.md`, `apps/jellyfin/manifest.yaml`

---

## Cluster Topology

| Node | Role | LAN IP | Notes |
|------|------|--------|-------|
| cluster-node-1 | control-plane, etcd | 192.168.50.96 | Hosts local-path state for Jellyfin, Immich Postgres, Navidrome |
| cluster-node-2 | control-plane, etcd | 192.168.50.226 | Hosts local-path state for k2, Radar, Immich ML cache |
| cluster-node-3 | control-plane, etcd | 192.168.50.94 | Hosts local-path state for Audiobookshelf |
| cluster-node-4 | worker (GPU) | 192.168.50.102 | Hosts local-path / hostPath state for Retrom, Open WebUI, Ollama model cache. Was NotReady when the audit ran, so Retrom was down |
| NAS (UGOS) | NFS server | 192.168.50.192 / 100.117.142.58 (Tailscale) | Accepted SPOF |

Storage classes: `local-path` (the default; data lives on one node's disk, and the PV gets a hard
`nodeAffinity` to that node) and `nas-nfs` (NFS on the NAS, reachable from every node).

---

## Tier 1 — Node-Bound SPOFs (service stays down until a specific node returns)

These services cannot be rescheduled to another node. When their node fails, the replacement
pod stays `Pending` with `volume node affinity conflict` / `untolerated taint node.kubernetes.io/unreachable`
until a person fixes the node.

| Service | Bound to | Why it is not HA | Recommendation |
|---------|----------|------------------|----------------|
| **Jellyfin** (`jellyfin`) | cluster-node-1 | <ul><li>`config` PVC (SQLite library DB, users, favorites, watch state) is `local-path` on node-1</li><li>`cache` PVC (transcode/image cache) is `local-path` on node-1</li><li>`replicas: 1`; Jellyfin cannot run active-active (single SQLite writer)</li><li>`RollingUpdate` strategy would briefly run two pods against one DB if `config` were on shared storage</li></ul> | <ul><li>Move `config` to replicated block storage (Longhorn RWO, 3 replicas). If NFS is used instead, mount with NFSv4.1 and locking enabled, never `nolock`</li><li>Replace the `cache` PVC with an `emptyDir` (all of it can be regenerated)</li><li>Set `strategy: Recreate`</li><li>Add `tolerationSeconds: 30` for `not-ready`/`unreachable` so failover takes about a minute</li></ul> |
| **Immich Postgres** (`immich/immich-postgres`) | cluster-node-1 | <ul><li>`postgres-data` PVC (all photo metadata, albums, faces, users) is `local-path` on node-1</li><li>Single Postgres instance, no replica</li><li>When it is down, `immich-server` is effectively down even though it runs elsewhere</li></ul> | <ul><li>Best: run Postgres with CloudNativePG (primary + 1 streaming replica, anti-affinity across nodes, automatic failover). Each instance can stay on local-path storage</li><li>Simpler: move `postgres-data` to Longhorn and keep `Recreate`</li><li>Add scheduled `pg_dump` backups to the NAS either way</li></ul> |
| **Immich ML** (`immich/immich-machine-learning`) | cluster-node-2 | <ul><li>`ml-cache` PVC (downloaded models) is `local-path` on node-2</li><li>The data is only a cache, but the PV's node affinity still pins the pod</li></ul> | <ul><li>Replace with `emptyDir` (models re-download on start), or put the cache on `nas-nfs`</li></ul> |
| **Navidrome** (`navidrome`) | cluster-node-1 | <ul><li>`data` PVC (SQLite DB: users, playlists, play counts, stars) is `local-path` on node-1</li><li>`replicas: 1` (single SQLite writer)</li></ul> | <ul><li>Move `data` to Longhorn RWO; keep `Recreate`</li><li>Lower the unreachable toleration to 30s</li></ul> |
| **Audiobookshelf** (`audiobookshelf`) | cluster-node-3 | <ul><li>`config` PVC (SQLite DB: users, listening progress, bookmarks) is `local-path` on node-3</li><li>`metadata` PVC (covers, cached metadata) is `local-path` on node-3</li><li>`replicas: 1`, `RollingUpdate`</li></ul> | <ul><li>Move `config` to Longhorn RWO</li><li>Move `metadata` to Longhorn or `nas-nfs` (no DB in it)</li><li>Switch to `strategy: Recreate`</li></ul> |
| **Retrom** (`retrom`) | cluster-node-4 | <ul><li>`config` and `data` PVCs are `local-path` on node-4, the GPU worker that is down most often</li><li>Retrom does not need a GPU, but its state ended up on the GPU node</li><li>`retrom-postgres` is on NFS (not node-bound), but it is mounted with `nolock` (see cross-cutting section)</li></ul> | <ul><li>Move `config` and `data` to Longhorn (or `nas-nfs` if they contain no SQLite)</li><li>Keep non-GPU workloads off node-4: add a `nvidia.com/gpu` `NoSchedule` taint to node-4</li></ul> |
| **k2** (`k2/k2`, StatefulSet) | cluster-node-2 | <ul><li>Hard `requiredDuringScheduling` node affinity to `cluster-node-2`</li><li>`data-k2-0` PVC is `local-path` on node-2</li><li>StatefulSet pods on an unreachable node are never replaced automatically (see cross-cutting section)</li><li>No manifest for it in this repo</li></ul> | <ul><li>Remove the node affinity unless k2 needs hardware that only node-2 has</li><li>Move `data-k2-0` to Longhorn</li><li>Commit its manifest under `apps/k2/` so it can be rebuilt</li></ul> |
| **Radar** (`radar`) | cluster-node-2 | <ul><li>`radar` PVC (2Gi) is `local-path` on node-2</li><li>`replicas: 1`, `Recreate`</li></ul> | <ul><li>If the data is a regenerable cache or history, use `emptyDir`; otherwise use Longhorn</li><li>Set `persistence.storageClass` in the Helm values</li></ul> |
| **Ollama / Open WebUI / GPU jobs** (`apps/ollama`, `apps/open-webui`) | cluster-node-4 | <ul><li>GPU inference can only run on node-4, the only GPU node. That binding is inherent</li><li>`huggingface-cache` hostPath PV (`/srv/models/huggingface`) is pinned to node-4</li><li>Open WebUI (a UI plus a SQLite DB, no GPU needed) stored its PVC on node-4 via local-path</li><li>Orphaned local-path PVs (`open-webui`, `kitaru-server-config`) and a `purge-ollama-models-node-4` Job stay `Pending` on node-4</li></ul> | <ul><li>Accept the GPU binding for model serving (a second GPU node is the only real fix)</li><li>Run Open WebUI on CPU nodes with its DB on Longhorn, so the UI stays up and only reports that the model backend is unavailable</li><li>Put the model cache on `nas-nfs` so a replacement GPU node can start without re-downloading</li><li>Clean up the orphaned PVs and the stuck Job</li></ul> |
| **Kubernetes API endpoint** | cluster-node-1 | <ul><li>`apiserver_endpoint: 192.168.30.222` (kube-vip VIP) is on the wrong subnet: the nodes are on `192.168.50.0/24`, so the VIP is unreachable even though kube-vip holds the lease</li><li>The admin kubeconfig points at `https://cluster-node-1:6443`, so `kubectl`, `helm` and `helmfile` fail whenever node-1 is down, even though node-2 and node-3 serve the API</li><li>cluster-node-4's agent is configured with `apiserver_endpoint=192.168.50.96` (node-1's IP)</li></ul> | <ul><li>Set `apiserver_endpoint` to a free `192.168.50.x` address outside the MetalLB pool (`.200–.220`) and outside DHCP, e.g. `192.168.50.199`, then re-run the Ansible playbook so kube-vip announces it and the cert gets the new SAN</li><li>Point the kubeconfig and node-4's agent at the VIP</li><li>Until then, keep a second kubeconfig context for `cluster-node-2:6443`</li></ul> |

---

## Tier 2 — Single-Replica Services (recover on their own, after a delay)

These services have no node-local state, so Kubernetes reschedules them. They are still down for
about 5–6 minutes after a node becomes unreachable (the default 300s `unreachable` toleration,
plus image pull and start time). StatefulSets in this tier do **not** recover on their own; see
"StatefulSets on a dead node" below.

### Traffic path (an outage here takes down many services)

| Service | Why it is not HA | Recommendation |
|---------|------------------|----------------|
| **CoreDNS** (`kube-system/coredns`) | <ul><li>`replicas: 1`; every in-cluster DNS lookup fails while it reschedules, which breaks almost every app</li><li>Managed by K3s's bundled manifest, so a manual `kubectl scale` is reverted when K3s restarts</li></ul> | <ul><li>Run 2 replicas with pod anti-affinity and a PDB (`minAvailable: 1`). Either disable the bundled CoreDNS (`--disable coredns`) and install the CoreDNS Helm chart via helmfile, or add a custom manifest under `/var/lib/rancher/k3s/server/manifests/` that K3s does not overwrite</li></ul> |
| **traefik-private** (`traefik-private/traefik-private`) | <ul><li>`replicas: 1`; every `*.priv.mlops-club.org` service goes down with it</li><li>No PDB, no anti-affinity</li></ul> | <ul><li>`deployment.replicas: 2`, `podDisruptionBudget.enabled: true`, plus `topologySpreadConstraints` across `kubernetes.io/hostname` in the Helm values</li></ul> |
| **Tailscale proxy for traefik-private** (`traefik-private/ts-traefik-private-*`, StatefulSet) | <ul><li>One proxy pod carries the Tailscale IP `100.95.181.95` for the private LoadBalancer</li><li>It is a StatefulSet, so a dead node leaves it stuck in `Terminating`</li></ul> | <ul><li>Use a Tailscale operator `ProxyGroup` with `replicas: 2` for the ingress (check that operator v1.92 supports `ProxyGroup` for this LoadBalancer/Ingress type), or expose traefik-private through a Tailscale `Ingress` backed by a ProxyGroup</li></ul> |
| **traefik-public** (`traefik-public/traefik-public`) | <ul><li>`replicas: 1`; every public `*.mlops-club.org` service goes down with it</li></ul> | <ul><li>Same as traefik-private: 2 replicas, PDB, topology spread</li></ul> |
| **Cloudflare tunnel connector** (`traefik-public/controlled-cloudflared-connector`) | <ul><li>`replicas: 1`; one `cloudflared` carries all public traffic</li></ul> | <ul><li>Run 2+ replicas. Cloudflare tunnels support several connectors on one tunnel and balance between them. Set the replica count in the ingress controller's Helm values and add anti-affinity</li></ul> |
| **Harbor** (`image-registry/*`) | <ul><li>`harbor-core`, `-portal`, `-registry` and `-jobservice` are single-replica Deployments</li><li>`harbor-database` (Postgres) and `harbor-redis` are single-replica StatefulSets on NFS mounted with `nolock`</li><li>Apps pull images from Harbor, so pods rescheduled during an outage can hit `ImagePullBackOff` while Harbor is also rescheduling</li><li>`harbor-registry` PVC is RWO</li></ul> | <ul><li>Make sure app images use `imagePullPolicy: IfNotPresent` with pinned tags so nodes keep cached images</li><li>Scale `core` and `portal` to 2 (stateless)</li><li>Move registry blob storage to MinIO/S3 (or an RWX NFS PVC) so `registry` can scale to 2</li><li>Keep the DB single-instance (or use CloudNativePG); see the `nolock` note</li></ul> |

### Control loops (an outage pauses reconciliation; traffic keeps flowing)

| Service | Why it is not HA | Recommendation |
|---------|------------------|----------------|
| cert-manager, cainjector, webhook | <ul><li>All `replicas: 1`. While the webhook is down, creating or updating cert-manager resources fails</li></ul> | <ul><li>Acceptable as-is (certificates last 90 days). Optional: `replicaCount: 2` for `webhook` with a PDB</li></ul> |
| external-dns, reflector, tailscale operator, cloudflare-tunnel-ingress-controller | <ul><li>`replicas: 1`; new DNS records, mirrored secrets and new ingresses are delayed</li></ul> | <ul><li>Acceptable as-is; existing state keeps working</li></ul> |
| MetalLB controller, csi-nfs-controller, local-path-provisioner | <ul><li>`replicas: 1`; new IP assignments and new NFS PV provisioning wait until the pod reschedules</li><li>Mounts of existing NFS volumes are unaffected (handled by the `csi-nfs-node` DaemonSet)</li></ul> | <ul><li>Acceptable as-is. Optional: `controller.replicas: 2` for csi-driver-nfs (it has leader election)</li></ul> |
| metrics-server, kube-state-metrics, OTel operator, OTel `gateway-collector`, GPU operator, NFD | <ul><li>`replicas: 1`. `gateway-collector` has a PDB with `maxUnavailable: 1`, which with one replica protects nothing</li><li>While they are down, HPA metrics, dashboards and telemetry stop</li></ul> | <ul><li>Acceptable as-is. Optional: run `gateway-collector` with 2 replicas so its PDB has an effect</li></ul> |

### Applications

| Service | State location | Why it is not HA | Recommendation |
|---------|----------------|------------------|----------------|
| come-follow-me-app, seminary-feedback, golden-rules-studio, loseit-agent, xtra-reviewer-mockup, nginx-priv, whoami (internal/external) | None (stateless) | <ul><li>`replicas: 1`; about 5 minutes of downtime when the node fails</li></ul> | <ul><li>`replicas: 2` + `topologySpreadConstraints` on `kubernetes.io/hostname` + PDB `minAvailable: 1`</li></ul> |
| personal-finance, personal-finance-tax-projection | NAS (`users/`) | <ul><li>`replicas: 1`, `Recreate`; the app writes files to NFS</li></ul> | <ul><li>Lower the unreachable toleration to 30s. Only scale to 2 after confirming the app tolerates concurrent writers to `users/`</li></ul> |
| immich-server, immich-valkey | NAS (`library`); Valkey is in-memory | <ul><li>`replicas: 1`. Also depends on Immich Postgres, which is node-bound (Tier 1)</li></ul> | <ul><li>`immich-server` can run 2 replicas (stateless apart from the NFS library). Fix Postgres first</li></ul> |
| MinIO (`minio`) | NAS (static NFS PV, RWO) | <ul><li>Single-node MinIO on NFS; reschedules, but has about 5 minutes of downtime</li></ul> | <ul><li>Acceptable (the NAS is the real SPOF). Lower the toleration</li></ul> |
| retrom-postgres | NAS (`nolock`, `hard`) | <ul><li>Single Postgres on NFS mounted with `nolock`</li></ul> | <ul><li>Keep `Recreate`; see the `nolock` note. Consider Longhorn or CloudNativePG</li></ul> |
| pebble | `emptyDir` (`captures`) | <ul><li>`replicas: 1`; captures are lost whenever the pod moves</li></ul> | <ul><li>Put captures on `nas-nfs` if they need to survive restarts</li></ul> |

---

## Tier 3 — Already HA

| Component | Why it is HA | Caveats |
|-----------|--------------|---------|
| etcd / K3s control plane | 3 servers with embedded etcd; quorum (2/3) survives losing one server | Losing two control-plane nodes loses quorum. The API endpoint itself is node-bound (Tier 1) |
| kube-vip DaemonSet | Runs on every control-plane node with leader election | The VIP address is unreachable (Tier 1) |
| MetalLB speaker, csi-nfs-node, GPU DaemonSets | One per node | No `LoadBalancer` services use MetalLB; traefik-private's LB is the Tailscale proxy |
| nginx-internal-https | `replicas: 2`, spread across node-2 and node-3 | The spread happened by chance: no anti-affinity or PDB guarantees it |

---

## Cross-Cutting Causes

### `local-path` is the default StorageClass

Any PVC without an explicit `storageClassName` lands on one node's disk with a hard node affinity.
This is the root cause of most Tier 1 findings.

**Recommendation**: install [Longhorn](https://longhorn.io) (block storage replicated across
node-1, node-2 and node-3; it needs `open-iscsi` on each node), make it the default StorageClass,
and migrate the Tier 1 PVCs one at a time: scale to 0, copy data, re-point the PVC, scale up.
Keep `nas-nfs` for bulk media.

### 300-second eviction delay

Pods on an unreachable node are only evicted after the default
`node.kubernetes.io/unreachable:NoExecute` toleration of 300s, so even stateless single-replica
services are down for about 5–6 minutes.

**Recommendation**: set the kube-apiserver flags `default-unreachable-toleration-seconds` and
`default-not-ready-toleration-seconds` to `30`, passed with `--kube-apiserver-arg` in
`extra_server_args` in `k3s-ansible/inventory/cluster/group_vars/all.yml`, or set
`tolerationSeconds` per workload.

### StatefulSets on a dead node

Kubernetes never replaces a StatefulSet pod whose node is unreachable. The old pod stays in
`Terminating`, and the controller waits for confirmation that it stopped, to avoid running two
copies with the same identity. This affects `harbor-database-0`, `harbor-redis-0`,
`ts-traefik-private-*` and `k2-0`. Deployments with RWO volumes on a dead node have the same
problem (the old Jellyfin pod stayed `Terminating` on node-1 for 117 days).

**Recommendation**: when a node is confirmed dead, apply the non-graceful shutdown taint
`kubectl taint node <node> node.kubernetes.io/out-of-service=nodeshutdown:NoExecute`. Kubernetes
then force-deletes the pods and detaches volumes. Remove the taint once the node returns.
Document this step in `.ai/howto/how-to-troubleshoot-kubernetes.md`.

### NFS mounted with `nolock`

Every NFS PV and the `nas-nfs` StorageClass use `nfsvers=3,nolock`. That is fine for media, but
it disables file locking for Postgres (`harbor-database`, `retrom-postgres`) and for any SQLite
moved onto NFS. If two pods ever run at once (for example during a `RollingUpdate`, or with a
stuck `Terminating` pod), the database can be corrupted.

**Recommendation**: keep databases off NFS (Longhorn or CloudNativePG). If a database has to
stay on NFS, use `Recreate`, mount with NFSv4.1 (which has built-in locking), and never scale
above 1.

### NFS server addressed by Tailscale IP

The NFS server is `100.117.142.58` (the NAS's Tailscale address), so each node's `tailscaled` is
in the storage data path. A Tailscale problem on one node takes away that node's storage.

**Recommendation**: use the NAS LAN address (`192.168.50.192`) for NFS PVs and the StorageClass.
This removes the per-node Tailscale dependency and the WireGuard overhead.

### No PodDisruptionBudgets

Only `gateway-collector` has a PDB. Node drains (for K3s upgrades or reboots) evict every
single-replica service on the node at once, with no coordination.

---

## Measure Availability Before Changing It

Uptime monitoring comes **before** any HA work. Without a baseline there is no way to tell whether
a change improved availability, and no data to rank the services in this document by actual
downtime rather than by guesswork. Collect 2–4 weeks of baseline data, then use it to order the
remediation list.

Combine three kinds of measurement. Each one catches failures the others miss.

### Outside-in (synthetic probes from off the cluster)

These see what a user sees, and keep working when the whole cluster is down.

- **Public paths** (`*.mlops-club.org`): use an external probe service such as UptimeRobot,
  Better Stack, or Cloudflare Health Checks. Probe each public hostname every 1–5 minutes. This
  exercises Cloudflare → tunnel connector → traefik-public → app.
- **Private paths** (`*.priv.mlops-club.org`): run [Gatus](https://github.com/TwiN/gatus) or
  Uptime Kuma *outside the cluster* on a Tailscale-connected host. The NAS (as a container) works:
  if the NAS is down, storage is down anyway. This exercises Tailscale → Tailscale proxy →
  traefik-private → app.
- **Kubernetes API**: probe `https://<vip>:6443/readyz` (and each server's `:6443/readyz`) from
  the same off-cluster host. This shows whether the VIP itself works, which is a Tier 1 finding.

### Inside-in (probes and signals from within the cluster)

These locate where in the chain a failure sits, and cover internal dependencies that have no
external URL.

- **In-cluster Gatus** (or Prometheus `blackbox_exporter`) probing each Service's ClusterIP
  health endpoint (`jellyfin:8096/health`, Immich `/api/server/ping`, Navidrome `/ping`,
  Audiobookshelf `/healthcheck`), plus DNS lookups through CoreDNS, the Harbor `/api/v2.0/health`
  endpoint, and a write/read/delete of a small file on an NFS PVC.
- **Comparing the two views pins down the failing layer**: if the inside probe passes but the
  outside probe fails, the problem is in ingress or tunnel; if both fail, it is the app or its
  state.
- **kube-state-metrics** (already deployed) provides `kube_deployment_status_replicas_available`
  and `kube_node_status_condition`. Recording these gives per-service "replicas available" time
  series and node-down windows without new probes. They need a metrics backend (Prometheus or
  VictoriaMetrics). The OTel `gateway-collector` can scrape them and forward them.

### Heartbeats (dead man's switch)

Probes only fire when something runs the probe. A heartbeat inverts that: the cluster pings an
external receiver on a schedule, and the receiver alerts when pings **stop**. This catches the
case where the whole cluster, or its outbound internet, is gone and in-cluster alerting has gone
with it.

- Run a `CronJob` every minute that `curl`s a [Healthchecks.io](https://healthchecks.io)
  (or a self-hosted Healthchecks on the NAS) ping URL.
- Use **one heartbeat per critical path**: make the CronJob first exercise the path (DNS lookup →
  HTTP GET through the ingress → NFS file write), then ping a distinct check for each path. If
  the Jellyfin path heartbeat stops but the cluster heartbeat continues, the failure is in that
  path.
- Run alerting (in-cluster Alertmanager, Gatus alerts) to the same channel, so one place shows
  "cluster up but service X down" alongside "cluster unreachable".

### Critical paths to monitor first

| Path | Outside-in probe | Inside-in probe / heartbeat |
|------|------------------|-----------------------------|
| Public ingress → app | External HTTP check per public hostname | CronJob GET through `traefik-public` Service |
| Private ingress → app | Off-cluster Gatus over Tailscale | CronJob GET through `traefik-private` Service |
| Cluster DNS | — | Gatus DNS check against CoreDNS |
| Kubernetes API (VIP + each server) | Off-cluster `/readyz` | kube-vip lease holder metric |
| NAS storage | — | CronJob NFS write/read/delete heartbeat |
| Image registry | — | Harbor `/api/v2.0/health` |
| Stateful apps (Jellyfin, Immich, Navidrome, Audiobookshelf, Retrom) | Hostname check | ClusterIP health endpoint + `replicas_available` |

### Using the data

- Track each service's **availability SLI** (successful probes ÷ total probes per 30 days) and
  **time to recover** from each node-down event (`kube_node_status_condition` gives the timing).
- Rank remediation work by **downtime minutes × importance of the service**. Re-measure after
  each change; a change that does not move the SLI or the recovery time gets reverted or rethought.
- A node-failure drill (cordon and power off one node during a maintenance window) produces a
  direct before/after comparison for each change.

---

## Prioritized Remediation

0. **Set up uptime measurement** (outside-in probes, inside-in probes, heartbeats; see above) and collect a baseline before making the changes below. Reorder the remaining items using that data.
1. **Fix the API endpoint**: move the kube-vip VIP into `192.168.50.0/24` and point kubeconfigs at it.
2. **Lower eviction tolerations** to 30s cluster-wide (one K3s flag change; speeds up recovery for every Tier 2 service).
3. **Make CoreDNS, traefik-private, traefik-public and cloudflared 2-replica** with spread and PDBs.
4. **Install Longhorn** and migrate Jellyfin, Navidrome, Audiobookshelf, Retrom, k2 and Radar state; convert pure caches (`jellyfin/cache`, `immich/ml-cache`) to `emptyDir`.
5. **Move Immich Postgres to CloudNativePG** (or Longhorn) with NAS backups.
6. **Taint node-4** for GPU-only workloads; move Open WebUI off it.
7. **Document the `out-of-service` taint** procedure for dead nodes.
8. **Scale stateless apps to 2 replicas** with topology spread and PDBs.
