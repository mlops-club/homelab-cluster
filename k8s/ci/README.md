# CI/CD Cluster Access Setup

**Purpose**: One-time setup for GitHub Actions to access the homelab cluster

**Scope**: RBAC manifests, kubeconfig generation, and GitHub Secrets configuration

**Overview**: Creates two ServiceAccounts with scoped RBAC — a read-only account for PR diffs
    and a cluster-admin account for deploys. Generates kubeconfigs that use Tailscale DNS
    to reach the API server, then stores them as base64-encoded GitHub Secrets.

**Dependencies**: kubectl access to the cluster, GitHub repo admin access, Tailscale admin access

**Exports**: Two kubeconfigs (readonly + deploy) stored as GitHub Secrets

**Related**: helmfile-diff.yml, helmfile-deploy.yml, rbac-readonly.yaml, rbac-deploy.yaml

**Implementation**: Long-lived ServiceAccount tokens with static kubeconfigs over Tailscale

---

## Step 1: Apply RBAC Manifests

```bash
kubectl apply -f k8s/ci/rbac-readonly.yaml
kubectl apply -f k8s/ci/rbac-deploy.yaml
```

Wait a few seconds for the token Secrets to be populated by the token controller.

## Step 2: Generate Kubeconfigs

```bash
# Extract tokens and CA
READONLY_TOKEN=$(kubectl get secret ci-readonly-token -n ci-system -o jsonpath='{.data.token}' | base64 -d)
DEPLOY_TOKEN=$(kubectl get secret ci-deploy-token -n ci-system -o jsonpath='{.data.token}' | base64 -d)
CA_DATA=$(kubectl get secret ci-readonly-token -n ci-system -o jsonpath='{.data.ca\.crt}')

# Generate readonly kubeconfig
cat <<EOF > /tmp/kubeconfig-readonly.yaml
apiVersion: v1
kind: Config
clusters:
  - cluster:
      certificate-authority-data: ${CA_DATA}
      server: https://cluster-node-1:6443
    name: homelab
contexts:
  - context:
      cluster: homelab
      user: ci-readonly
    name: ci-readonly@homelab
current-context: ci-readonly@homelab
users:
  - name: ci-readonly
    user:
      token: ${READONLY_TOKEN}
EOF

# Generate deploy kubeconfig
cat <<EOF > /tmp/kubeconfig-deploy.yaml
apiVersion: v1
kind: Config
clusters:
  - cluster:
      certificate-authority-data: ${CA_DATA}
      server: https://cluster-node-1:6443
    name: homelab
contexts:
  - context:
      cluster: homelab
      user: ci-deploy
    name: ci-deploy@homelab
current-context: ci-deploy@homelab
users:
  - name: ci-deploy
    user:
      token: ${DEPLOY_TOKEN}
EOF

# Base64 encode for GitHub Secrets
echo "=== KUBECONFIG_READONLY_B64 ==="
base64 -i /tmp/kubeconfig-readonly.yaml
echo ""
echo "=== KUBECONFIG_DEPLOY_B64 ==="
base64 -i /tmp/kubeconfig-deploy.yaml

# Clean up
rm /tmp/kubeconfig-readonly.yaml /tmp/kubeconfig-deploy.yaml
```

## Step 3: Create Tailscale OAuth Client for CI

1. Go to https://login.tailscale.com/admin/settings/oauth
2. Create a new OAuth client:
   - **Description**: `github-actions-homelab-ci`
   - **Tags**: `tag:ci`
3. Add ACL entry at https://login.tailscale.com/admin/acls:

```jsonc
{
  "tagOwners": {
    "tag:ci": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:ci"],
      "dst": ["cluster-node-1:6443"]
    }
  ]
}
```

## Step 4: Configure GitHub Secrets

Go to repo Settings > Secrets and variables > Actions.

**Secrets** (sensitive):

| Secret | Source |
|--------|--------|
| `CLOUDFLARE_API_TOKEN` | `~/credentials/homelab.env` |
| `CLOUDFLARE_ACCOUNT_ID` | `.env` |
| `CLOUDFLARE_ZONE_ID` | `.env` |
| `TAILSCALE_CLIENT_ID` | `~/credentials/homelab.env` (in-cluster operator OAuth) |
| `TAILSCALE_CLIENT_SECRET` | `~/credentials/homelab.env` |
| `ACME_EMAIL` | `.env` |
| `HARBOR_ADMIN_PASSWORD` | `~/credentials/homelab.env` |
| `HARBOR_SECRET_KEY` | `~/credentials/homelab.env` |
| `TS_OAUTH_CLIENT_ID` | From Step 3 (CI-specific OAuth, separate from cluster) |
| `TS_OAUTH_CLIENT_SECRET` | From Step 3 |
| `KUBECONFIG_READONLY_B64` | From Step 2 |
| `KUBECONFIG_DEPLOY_B64` | From Step 2 |

**Variables** (non-sensitive):

| Variable | Value |
|----------|-------|
| `DOMAIN` | `mlops-club.org` |
| `CLOUDFLARE_DOMAIN` | `mlops-club.org` |
| `NFS_SERVER` | `nas` |
| `NFS_SHARE` | `/volume1/k8s-homelab` |
| `NFS_STORAGE_CLASS_NAME` | `nas-nfs` |
| `NFS_NAMESPACE` | `nfs-system` |
| `NFS_MOUNT_OPTIONS` | `nfsvers=3,nolock` |

## Step 5: Create GitHub Environment

Go to repo Settings > Environments > New environment.

- **Name**: `production`
- **Required reviewers**: add yourself
- **Deployment branches**: select "Selected branches" > add `main`

Optionally scope `KUBECONFIG_DEPLOY_B64` as an environment secret (only available in `production`).
