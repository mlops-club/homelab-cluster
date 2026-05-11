# homelab-cluster - Project Context

**Purpose**: Project development context for AI agents working on homelab-cluster

**Scope**: Mission, architecture, key patterns, and directory structure

**Overview**: Primary context document for AI agents. Describes what homelab-cluster does, how it works,
    and key patterns to follow. Peer document to ai-rules.md; together with index.yaml they form
    the three core documents every agent reads first.

**Dependencies**: AGENTS.md (entry point), ai-rules.md (mandatory rules), index.yaml (navigation)

**Exports**: Project context, architectural patterns, development guidelines

**Related**: ai-rules.md for mandatory rules, index.yaml for navigation

---

## Mission

Bare-metal Kubernetes homelab running K3s on Intel NUCs, providing production services for the MLOps Club with dual-stack networking (private via Tailscale, public via Cloudflare Tunnel), NFS-backed persistent storage, and a private container registry.

**Type**: infrastructure
**Status**: in-development

## Architecture

homelab-cluster uses a bare-metal K3s infrastructure architecture built on:

- **K3s** - Lightweight Kubernetes distribution deployed across Intel NUC nodes with etcd HA
- **Ansible** - Cluster provisioning and node configuration via `k3s-ansible/` playbooks
- **Helm** - Package management for all cluster components (cert-manager, Traefik, external-dns, etc.)
- **Dual-stack networking** - Private services via Tailscale VPN, public services via Cloudflare Tunnel
- **Shell scripts** - Automation for bootstrap, network setup, and app deployment
- **GitHub Actions** - CI/CD pipelines for linting and Molecule-based integration testing
- **AWS CDK** - Disaster recovery / cloud fallback infrastructure (minimal)

## Key Patterns

- **Idempotent bootstrap** - `bootstrap.sh` can be run repeatedly to converge the cluster to desired state
- **Helm-install scripts** - Each network layer has a `helm-install.sh` that installs/upgrades all components in dependency order
- **Namespace-per-app** - Each application gets its own Kubernetes namespace with dedicated resources
- **Private/public split** - Two Traefik instances: `traefik-private` (Tailscale, `*.priv.mlops-club.org`) and `traefik-public` (Cloudflare, `*.mlops-club.org`)
- **NAS-backed storage** - NFS CSI driver connects to a home NAS (UGOS) for persistent volumes; Harbor registry uses NAS storage; static PVs for human-readable media paths (`/volume1/k8s-homelab/media/`)
- **Mermaid diagrams** - Architecture diagrams use Mermaid in markdown

## Directory Structure

```
homelab-cluster/
├── AGENTS.md                   # Primary AI agent entry point
├── CLAUDE.md                   # Claude IDE config
├── .ai/
│   ├── ai-context.md           # Project context (this file)
│   ├── ai-rules.md             # Mandatory rules
│   ├── index.yaml              # Navigation index
│   ├── docs/                   # Conceptual documentation
│   ├── howto/                  # Procedural how-to guides
│   └── templates/              # Reusable templates
├── k3s-ansible/                # Ansible playbooks for K3s cluster deployment
│   ├── roles/                  # 13 Ansible roles (k3s_server, k3s_agent, prereq, etc.)
│   ├── inventory/              # Cluster node definitions
│   ├── molecule/               # Testing framework (Vagrant-based)
│   └── site.yml                # Main playbook
├── network/
│   ├── private/                # Internal services (Tailscale VPN)
│   │   ├── cert-manager/       # Let's Encrypt TLS provisioning
│   │   ├── tailscale/          # Tailscale operator integration
│   │   ├── external-dns/       # Cloudflare DNS automation
│   │   ├── traefik/            # Private ingress (*.priv.mlops-club.org)
│   │   └── helm-install.sh     # Install all private network components
│   └── public/                 # External-facing services
│       ├── cloudflare-tunnel-ingress-controller/  # Tunnel to Cloudflare
│       ├── traefik/            # Public ingress (*.mlops-club.org)
│       └── helm-install.sh     # Install all public network components
├── storage/                    # Persistent storage & Harbor registry
│   └── nfs/                    # NFS CSI driver (NAS-backed)
├── apps/                       # Business applications
│   ├── audiobookshelf/         # Self-hosted audiobook server (NFS-backed media)
│   ├── come-follow-me-app/     # Rust backend app
│   └── seminary-feedback/      # Feedback collection app
├── aws/                        # AWS CDK infrastructure (DR/cloud fallback)
├── image-registry/             # Harbor private container registry
├── bootstrap.sh                # Main cluster bootstrap script (idempotent)
├── BOOTSTRAP.md                # Step-by-step setup guide
├── prek.toml                   # Git hook configuration (secret scanning, conventional commits)
├── env.example                 # Environment variable template
└── .github/
    └── workflows/              # CI/CD (lint, Molecule tests)
```

## Physical Infrastructure

The cluster runs on physical Intel NUC machines on a home LAN:
- NUC nodes on `192.168.50.x` subnet
- MetalLB assigns service IPs from `192.168.50.200-192.168.50.220`
- kube-vip provides a control plane VIP
- NAS (UGOS) provides NFS storage and hosts Harbor registry data
- Network interface: `enp1s0` (not eth0)
- Timezone: `America/Denver`

## Networking Architecture

### Private Path
Tailscale VPN → External-DNS (Cloudflare) → cert-manager (Let's Encrypt) → Traefik Private → Services

Services are accessible at `*.priv.mlops-club.org` via Tailscale only. External-DNS automatically creates DNS records pointing to Traefik's Tailscale IP. TLS uses a wildcard cert (`priv-wildcard-tls`).

### Public Path
Internet → Cloudflare (TLS termination) → Cloudflare Tunnel → Traefik Public → Services

Services are accessible at `*.mlops-club.org` from the public internet. Cloudflare handles TLS at the edge; traffic reaches Traefik via HTTP through the tunnel. Uses `*.mlops-club.org` single-level wildcard for Cloudflare's free Universal SSL.

## Environment Configuration

The cluster requires a `.env` file (gitignored) with:
- `CLOUDFLARE_API_TOKEN` - Zone:Read, Zone:DNS:Edit, Account:Cloudflare Tunnel:Edit
- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ZONE_ID` - Cloudflare identifiers
- `TAILSCALE_CLIENT_ID`, `TAILSCALE_CLIENT_SECRET` - Tailscale OAuth
- `ACME_EMAIL` - Let's Encrypt notifications
- `DOMAIN` - Primary domain (e.g., `mlops-club.org`)

## CI/CD

GitHub Actions runs on PRs:
- **Lint**: prek checks + GitHub Action SHA pinning verification
- **Test**: Molecule-based integration tests (5 scenarios: default, single_node, calico, cilium, kube-vip) using Vagrant/VirtualBox on self-hosted runners
