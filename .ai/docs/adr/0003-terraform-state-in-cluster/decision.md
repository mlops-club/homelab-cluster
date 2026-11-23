# ADR 0003: Terraform State in the Cluster (Kubernetes Backend)

**Purpose**: Record where Terraform state for homelab infrastructure lives: in a Kubernetes Secret in the homelab cluster, locked with a Lease, one Secret per Terraform folder

**Scope**: Every Terraform root module in this repository. The first and, so far, only one is `monitoring/terraform/` (Grafana Cloud, [ADR 0001](../0001-outside-in-monitoring/decision.md)); the convention covers future ones (Studio telemetry, Cloudflare)

**Overview**: Terraform's `kubernetes` backend stores the state, gzip-compressed, in a Secret and takes a
    Lease as the lock. No new cloud account, no new service to run, and the cluster already has
    replicated storage for Secrets (embedded etcd on three servers). The cost is that Terraform needs a
    working kubeconfig, and a Secret holds at most 1 MB. The decision is independent of what the
    Terraform manages; the Grafana folder was simply the first state to move

**Dependencies**: `monitoring/terraform/versions.tf` (backend block), the homelab kubeconfig (`~/.kube/config`)

**Exports**: The one-folder-one-Secret convention, the `terraform-state` namespace

**Related**: [ADR 0001](../0001-outside-in-monitoring/decision.md) (first consumer), `.github/workflows/helmfile-deploy.yml` (how CI already reaches the cluster over the tailnet)

---

**Status**: Accepted

## Context

- `monitoring/terraform/terraform.tfstate` lived in one git worktree on one laptop. A second worktree,
  another person or CI could not plan without copying it, and nothing stopped two applies at once.
- The state holds secrets: the probe token, public dashboard tokens, the Discord webhook URL. It must not
  be committed, and wherever it lives must be access-controlled.
- The owner prefers not to add cloud dependencies the homelab doesn't already have.

## Options considered

| Option | Locking | New dependency | Why not (or why) |
|---|---|---|---|
| Local file (status quo) | None | None | Tied to one checkout; no locking; easy to lose |
| HCP Terraform (free tier) | Yes | HashiCorp account; state and secrets on their servers | A new cloud dependency holding secrets |
| S3-compatible bucket (AWS S3, Cloudflare R2) | S3 native lock file | A bucket, credentials, a cloud account per collaborator | A new cloud dependency; credentials to hand out |
| Postgres backend (`pg`) on an in-cluster database | Advisory locks | A database to run, back up and expose | More to operate than a Secret |
| **Kubernetes backend** | **Lease** | **None: the cluster already exists** | **Chosen** |

## Decision

```hcl
# monitoring/terraform/versions.tf
backend "kubernetes" {
  secret_suffix = "grafana-monitoring"
  namespace     = "terraform-state"
  config_path   = "~/.kube/config"
}
```

| Term | Plain meaning | Example in this setup |
|---|---|---|
| **State** | Terraform's record of what it created, with every attribute, including secrets | The Grafana checks, SLOs, dashboards, the probe token |
| **Backend** | Where Terraform reads and writes the state | `kubernetes` |
| **Root module** | A folder you run `terraform plan` in; it has exactly one state | `monitoring/terraform/` |
| **Lock** | A marker that makes a second `plan`/`apply` wait or fail while one is running | Lease `terraform-state/lock-tfstate-default-grafana-monitoring` |

**Convention: one root module = one state = one Secret** in namespace `terraform-state`, named
`tfstate-default-<secret_suffix>`, with `secret_suffix` named after the folder's system. Split folders by
system and by credentials (Grafana monitoring, Studio telemetry, a future Cloudflare setup), not by size.

## The chicken-and-egg question, resolved

The Grafana monitoring stack's state lives here, and the way to see that this state works is to run the
Grafana stack. That doesn't make the two decisions depend on each other: this ADR needs *a* Terraform
folder to prove itself on, not the monitoring decision. The Grafana folder existed first with a local
state file, which made it the natural first migration. The tests below exercise the backend itself
(round trip, lock, size) and would pass for any folder. So the order is: this ADR stands alone; ADR 0001
depends on it for where its state lives.

## Verification

| Test | Command | Result |
|---|---|---|
| Migrate | `terraform init -migrate-state` | State copied into Secret `terraform-state/tfstate-default-grafana-monitoring` |
| Round trip | Move the local `terraform.tfstate` away, then `./tf plan` | "No changes": every resource read back from the Secret |
| Lock | A second `./tf plan` while one is running | Fails with "Error acquiring the state lock" (Lease held) |
| Size | `kubectl -n terraform-state get secret tfstate-default-grafana-monitoring -o jsonpath='{.data.tfstate}' \| wc -c` | 263,740 bytes of the 1 MB limit; most of it is the two dashboards' embedded formula images |
| Daily use | Every change in [ADR 0001](../0001-outside-in-monitoring/decision.md) (20 applies) | Applied through the Secret with no lock errors |

## Consequences

- Terraform needs a kubeconfig for the homelab cluster to plan or apply. When the cluster is down,
  Grafana resources can't be changed (they keep running in Grafana Cloud).
- Anyone who can read Secrets in `terraform-state` can read every secret in the state. Keep that
  namespace's RBAC to cluster admins and, later, one CI service account.
- The state is as durable as the cluster's datastore: embedded etcd replicated across the three
  control-plane nodes. K3s takes local etcd snapshots by default; copying them off the nodes is not set up.
- A Secret holds at most 1 MB (gzip-compressed state, then base64). The Grafana state is about a quarter
  of that. Keep large embedded content out of Terraform-managed resources, or split the folder.

## Follow-ups

1. Run Terraform from GitHub Actions: join the tailnet the way `helmfile-deploy.yml` does, with a
   kubeconfig whose service account can only read and write Secrets and Leases in `terraform-state`.
2. Copy etcd snapshots (or `terraform state pull`, encrypted) to the NAS.
3. Delete the gitignored local copies left from the migration (`terraform.pre-k8s-backend.tfstate`,
   `terraform.tfstate.migrated-local`, `terraform.tfstate.backup`) once the owner is comfortable.
