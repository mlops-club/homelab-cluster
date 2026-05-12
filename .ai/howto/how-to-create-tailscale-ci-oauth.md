# How-To: Create a Tailscale OAuth Client for GitHub Actions CI

**Purpose**: Create a dedicated Tailscale OAuth client that allows GitHub Actions runners to join the tailnet and reach the cluster API server

**Scope**: Tailscale ACL configuration and OAuth client creation for CI/CD pipeline connectivity

**Overview**: The GitHub Actions helmfile workflows need to connect to the homelab cluster via Tailscale
    to run `helmfile diff` (on PRs) and `helmfile apply` (on merge). This requires a separate OAuth
    client from the one used by the in-cluster tailscale-operator. The CI OAuth client creates
    ephemeral Tailscale nodes tagged with `tag:ci` that are automatically cleaned up when the
    workflow completes. The `tag:ci` ACL tag restricts CI runners to only reach the K8s API server.

**Dependencies**: Tailscale admin access, Access Controls (ACL) editor access

**Exports**: OAuth Client ID and Client Secret for use as GitHub Secrets (`TS_OAUTH_CLIENT_ID`, `TS_OAUTH_CLIENT_SECRET`)

**Related**: helmfile-diff.yml, helmfile-deploy.yml, k8s/ci/README.md

**Implementation**: Two-step process — first add `tag:ci` to ACLs, then create the OAuth client with that tag

**Difficulty**: beginner

---

## Prerequisites

- Admin access to the Tailscale admin console
- The tailnet must already have the homelab cluster nodes joined

## Step 1: Add `tag:ci` to the ACL Policy

The OAuth client needs a tag to assign to CI runner devices. This tag must exist in the ACL `tagOwners` before the OAuth client can use it.

1. Navigate to **Access controls** > **JSON editor**
   - URL: `https://login.tailscale.com/admin/acls/file`

2. Find the `tagOwners` section in the ACL file

3. Add `"tag:ci": ["autogroup:admin"],` to the `tagOwners` block:

```jsonc
"tagOwners": {
    // k3s operator
    "tag:k8s-operator": [],
    "tag:k8s":      ["tag:k8s-operator"],
    "tag:homelab": ["autogroup:admin"],
    "tag:ci":      ["autogroup:admin"],   // <-- add this line
},
```

4. Click **Save**

> **Note on ACL rules**: The current tailnet uses a permissive wildcard grant (`"src": ["*"], "dst": ["*"]`) that already allows CI devices to reach the cluster. If you later tighten the grants to be restrictive, add a specific grant for CI:
> ```jsonc
> {
>     "src": ["tag:ci"],
>     "dst": ["cluster-node-1"],
>     "ip": ["*"],
> },
> ```

## Step 2: Create the OAuth Client

1. Navigate to **Settings** > **Trust credentials**
   - URL: `https://login.tailscale.com/admin/settings/trust-credentials`

2. Click the **+ Credential** button (top right of the content area)

3. **Step 1 — Settings**:
   - Select **OAuth** (should be selected by default)
   - Enter description: `github-actions-homelab-ci`
   - Click **Continue**

4. **Step 2 — Scopes**:
   - Leave the scope dropdown as **Custom scopes**
   - Expand **Devices** section:
     - Check **Core** > **Read**
   - Expand **Keys** section:
     - Check **Auth Keys** > **Write** (this auto-checks Read)
   - A **Tags** field appears below Auth Keys (required for write scope):
     - Click the "Add tags" dropdown
     - Select **tag:ci**
   - Leave all other scopes unchecked

5. Click **Generate credential**

6. **Copy both values immediately** — the Client Secret is only shown once:
   - **Client ID** → store as GitHub Secret `TS_OAUTH_CLIENT_ID`
   - **Client Secret** → store as GitHub Secret `TS_OAUTH_CLIENT_SECRET`

## Scope Rationale

| Scope | Why |
|-------|-----|
| Devices > Core > Read | The `tailscale/github-action` needs to see device information when joining the tailnet |
| Keys > Auth Keys > Write | The action generates an ephemeral auth key to register the CI runner as a temporary device |
| tag:ci | Tags the CI runner device so ACL rules can scope its network access |

## What Happens at Runtime

When a GitHub Actions workflow runs:

1. The `tailscale/github-action` uses the OAuth Client ID + Secret to authenticate with the Tailscale API
2. It generates an ephemeral auth key tagged with `tag:ci`
3. It starts the Tailscale daemon on the runner and joins the tailnet using that key
4. The runner can now resolve `cluster-node-1` via Tailscale MagicDNS and reach port 6443
5. When the workflow completes, the ephemeral node is automatically removed from the tailnet

## Verification

After creating the OAuth client, verify it appears in the Trust credentials list:
- Navigate to `https://login.tailscale.com/admin/settings/trust-credentials`
- Confirm a second OAuth client exists with scopes `devices:core, auth_keys` and the `tag:ci` tag

## Troubleshooting

**"tag not found" when selecting tags**: Make sure you saved the ACL file in Step 1 before creating the OAuth client. The tag must exist in `tagOwners` first.

**CI runner can't reach the cluster**: Check that the ACL grants allow `tag:ci` to reach `cluster-node-1:6443`. Run `tailscale status` in the CI workflow to verify the runner joined the tailnet.

**"unauthorized" errors**: The Client Secret may have been copied incorrectly, or the OAuth client may have been deleted/regenerated. Create a new OAuth client and update the GitHub Secrets.
