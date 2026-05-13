# How-To: Bootstrap the Cluster

**Purpose**: Guide AI agents through bootstrapping the K3s cluster from scratch

**Scope**: Complete cluster setup from bare nodes to fully operational with networking, storage, and apps

**Overview**: Distills the bootstrap process documented in BOOTSTRAP.md into an agent-friendly
    procedural format. Covers prerequisites, environment setup, Ansible deployment, network
    stack installation, and verification. The bootstrap script is idempotent and safe to re-run.

**Dependencies**: Intel NUC nodes with SSH access, Tailscale account, Cloudflare account, NAS for storage, helmfile, helm, helm-diff plugin

**Exports**: A fully operational K3s cluster with private and public networking

**Related**: BOOTSTRAP.md, README.md, bootstrap.sh, helmfile.yaml.gotmpl, k3s-ansible/README.md

**Implementation**: Scripted bootstrap with manual prerequisite verification; helmfile manages all Helm releases

**Difficulty**: advanced

---

## Prerequisites

### Manual Setup (must be done by a human)

1. **Environment file**: Create `.env` from `env.example` with all credentials
   - `CLOUDFLARE_API_TOKEN` (Zone:Read, Zone:DNS:Edit, Account:Cloudflare Tunnel:Edit)
   - `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ZONE_ID`
   - `TAILSCALE_CLIENT_ID`, `TAILSCALE_CLIENT_SECRET`
   - `ACME_EMAIL`
   - `DOMAIN` (e.g., `mlops-club.org`)

2. **Tailscale**: Install daemon and join the tailnet on the machine running kubectl

3. **Ansible inventory**: Configure node information in:
   - `k3s-ansible/inventory/cluster/hosts.ini` — node IPs and roles
   - `k3s-ansible/inventory/cluster/group_vars/all.yml` — cluster settings

4. **SSH access**: Verify passwordless SSH to all cluster nodes

## Steps

### Step 1: Verify Prerequisites

```bash
# Check .env exists
test -f .env && echo "OK" || echo "MISSING: Create .env from env.example"

# Check SSH to nodes
ssh main@cluster-node-1 "hostname"

# Check Tailscale is connected
tailscale status
```

### Step 2: Run Bootstrap

```bash
./bootstrap.sh
```

The script is idempotent and performs these operations in order:
1. Validates prerequisites (`.env`, inventory, SSH, helmfile, helm-diff)
2. Bootstraps K3s cluster via Ansible
3. Configures kubeconfig for local kubectl access
4. Deploys all infrastructure via `helmfile apply` (cert-manager, reflector, tailscale-operator, external-dns, traefik-private, cloudflare-tunnel, traefik-public, csi-driver-nfs, harbor)

To also deploy example apps:
```bash
DEPLOY_EXAMPLES=true ./bootstrap.sh
```

### Step 3: Verify Cluster

```bash
# Nodes are ready
kubectl get nodes -o wide

# All Helm releases are deployed
helm list -A

# System pods are running
kubectl get pods -A

# Verify helmfile sees no drift
source .env && helmfile -f helmfile.yaml.gotmpl diff
```

### Step 4: Verify Networking

```bash
# Private: test via Tailscale
curl -s https://whoami.priv.mlops-club.org

# Public: test via Cloudflare
curl -s https://whoami.mlops-club.org
```

### Step 5: Deploy Apps (if not done via DEPLOY_EXAMPLES)

```bash
# Deploy individual apps
./apps/<app-name>/deploy.sh
```

## Teardown

To completely tear down the cluster:

```bash
cd k3s-ansible && ./run reset
```

**Warning**: This destroys the cluster and regenerates x509 certificates. After reset, the kubeconfig in `~/.kube/config` is invalid and must be refreshed (see README.md).

## Success Criteria

- [ ] All nodes are in `Ready` state
- [ ] All system pods are running
- [ ] Private networking is operational (Tailscale + Traefik + DNS)
- [ ] Public networking is operational (Cloudflare Tunnel + Traefik)
- [ ] Applications are accessible via their domains
