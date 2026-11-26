# Node Registry

**Purpose**: Single inventory of every node in the homelab cluster: hardware, architecture, role, network, and how it is provisioned

**Scope**: All k3s nodes, control plane and workers

**Overview**: One row per node plus the conventions every node shares. The cluster is mixed-architecture
    (amd64 NUCs and GPU box, arm64 MacBook Pro), which is the main thing a workload author has to account
    for. Update this file whenever a node is added, removed, re-provisioned, or changes role.

**Dependencies**: `k3s-ansible/inventory/cluster/hosts.ini` (Ansible-managed nodes), `macbook-node/` (MacBook nodes)

**Exports**: Node names, roles, architectures, provisioning method per node

**Related**: `.ai/docs/CLUSTER_HA_AUDIT.md`, `.ai/docs/adr/0006-macbook-cluster-node/decision.md`, `gpu-operator/README.md`, `.ai/ai-rules.md` (Container Image Rules)

---

## Nodes

| Node | Hardware | Arch | CPU / RAM | Disk | OS / kernel | Role | LAN IP / uplink | Provisioned by |
|---|---|---|---|---|---|---|---|---|
| `cluster-node-1` | GMKtec NucBox G2 (Intel N100) | amd64 | 4 cores / 12 GB | 512 GB NVMe | Ubuntu 20.04, 5.15 | control plane, etcd | 192.168.50.96 / wired `enp1s0` | Ansible (`k3s-ansible/`) |
| `cluster-node-2` | GMKtec NucBox G2 (Intel N100) | amd64 | 4 cores / 12 GB | 512 GB NVMe | Ubuntu 20.04, 5.15 | control plane, etcd | 192.168.50.226 / wired `enp1s0` | Ansible |
| `cluster-node-3` | GMKtec NucBox G2 (Intel N100) | amd64 | 4 cores / 12 GB | 512 GB NVMe | Ubuntu 20.04, 5.15 | control plane, etcd; holds the kube-vip lease | 192.168.50.94 / wired `enp1s0` | Ansible |
| `cluster-node-4` | Desktop with NVIDIA RTX 5080 (16 GB) | amd64 | 8 cores / 32 GB | — | Ubuntu 24.04, 7.0 | worker (GPU), labels/tags `gpu` | 192.168.50.102 / wired `enp7s0` | Ansible + `gpu-operator/` |
| `cluster-node-5` | MacBook Pro (Apple M2 Max, 32 GB) running a Lima VM | **arm64** | 12 vCPU / 24 GiB | 256 GiB sparse virtual disk | Ubuntu 24.04, 6.8 (guest) | worker | 192.168.50.136 / Wi-Fi bridged | `macbook-node/` ([ADR 0006](adr/0006-macbook-cluster-node/decision.md)) |

## Shared conventions

- **k3s v1.30.2+k3s2** everywhere; agents join `https://192.168.50.96:6443`.
- **DHCP clients** on 192.168.50.0/24. Addresses are stable because the router re-issues the same
  lease to the same MAC; none is pinned by a reservation.
- **Tailscale** on every node as `cluster-node-N`, `tag:homelab`, Tailscale SSH on
  (`ssh main@cluster-node-N`). The `nas-nfs` StorageClass reaches the NAS at its Tailscale IP, so a node
  must be on the tailnet to mount NFS volumes.
- **Flannel VXLAN** over each node's LAN interface (`flannel-iface`).

## Mixed architecture

The cluster runs `linux/amd64` (nodes 1–4) and `linux/arm64` (node 5). The scheduler does not check an
image's architectures, and a pod that cannot pull on its node retries there indefinitely; it is never
moved to another node. Therefore:

- Every image we build is multi-arch (`docker buildx build --platform linux/amd64,linux/arm64`).
- A third-party image with one architecture is pinned with `nodeSelector: {kubernetes.io/arch: amd64}`
  (Harbor is pinned this way in `image-registry/values.yaml`).
- See Container Image Rules in `.ai/ai-rules.md` and Step 5 of `.ai/howto/how-to-deploy-a-new-app.md`.

## Per-node notes

- **cluster-node-4** is often NotReady; GPU workloads are bound to it. See `gpu-operator/README.md`
  and the HA audit.
- **cluster-node-5** is a laptop: Wi-Fi uplink with variable latency, memory given to the VM is not
  returned to macOS, and `macbook-node/host-setup.sh pause` takes it offline before travel. It is
  excluded from MetalLB announcements (`node.kubernetes.io/exclude-from-external-load-balancers`). See
  the Limitations section of ADR 0006.

## Adding a node

1. Pick the next free `cluster-node-N` name (check the Tailscale machines list too).
2. Provision it: Ansible for Linux hosts (`k3s-ansible/`, see `BOOTSTRAP.md`); for Apple Silicon Macs
   follow `.ai/howto/how-to-add-a-macbook-node.md`.
3. Join Tailscale as `cluster-node-N` with `tag:homelab` and `--ssh`.
4. Add a row to this table and, if it changes a single point of failure, update
   `.ai/docs/CLUSTER_HA_AUDIT.md`.
