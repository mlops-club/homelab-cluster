# Cluster Bootstrap Guide

This guide provides instructions for bootstrapping the k3s cluster and deploying all network components from scratch.

## Manual Prerequisites

These steps must be completed manually before running the bootstrap script.

### 1. Environment Configuration

- Create `.env` file from `env.example`
- Fill in required credentials (see [`env.example`](env.example) for details)
- **Note**: This must be done manually before running bootstrap script

Required variables:
- `CLOUDFLARE_API_TOKEN` - Cloudflare API token with Zone:Read, Zone:DNS:Edit, and Account:Cloudflare Tunnel:Edit permissions
- `CLOUDFLARE_ACCOUNT_ID` - Cloudflare account ID
- `CLOUDFLARE_ZONE_ID` - Cloudflare zone ID for your domain
- `TAILSCALE_CLIENT_ID` - Tailscale OAuth client ID
- `TAILSCALE_CLIENT_SECRET` - Tailscale OAuth client secret
- `ACME_EMAIL` - Email address for Let's Encrypt certificate notifications
- `DOMAIN` - Your domain name (e.g., `mlops-club.org`)
- `CLOUDFLARE_DOMAIN` - Same as `DOMAIN` if not explicitly set

### 2. Tailscale Setup

- Install Tailscale daemon and join tailnet
- See [README.md](README.md) for Tailscale setup details

### 3. Inventory Configuration

- Configure `k3s-ansible/inventory/cluster/hosts.ini` with your cluster node information
- Configure `k3s-ansible/inventory/cluster/group_vars/all.yml` with cluster settings
- See [k3s-ansible/README.md](k3s-ansible/README.md) for details

### 4. SSH Access

- Verify SSH access to all cluster nodes listed in `k3s-ansible/inventory/cluster/hosts.ini`
- Ensure passwordless SSH is configured or have credentials ready for Ansible

## Automated Bootstrap

Once all prerequisites are complete, run:

```bash
./bootstrap.sh
```

To deploy example applications along with the cluster:

```bash
DEPLOY_EXAMPLES=true ./bootstrap.sh
```

The bootstrap script is idempotent and can be run multiple times safely. It will:

1. Validate prerequisites (`.env` file, inventory files, SSH access)
2. Bootstrap the k3s cluster using Ansible
3. Configure kubeconfig for local kubectl access
4. Seed required Kubernetes secrets
5. Install private network components (cert-manager, reflector, tailscale, external-dns, certificate, traefik-private)
6. Install public network components (Cloudflare Tunnel, traefik-public)
7. Optionally deploy example applications
8. Verify deployment status

For detailed information about what the script does, see the implementation in [`bootstrap.sh`](bootstrap.sh).

## Component Documentation

- **Private Network**: See [network/private/README.md](network/private/README.md)
- **Public Network**: See [network/public/README.md](network/public/README.md)
- **cert-manager Setup**: See [network/private/cert-manager/LETSENCRYPT_SETUP.md](network/private/cert-manager/LETSENCRYPT_SETUP.md)
- **Tailscale Operator**: See [network/private/tailscale/TAILSCALE_OPERATOR_SETUP.md](network/private/tailscale/TAILSCALE_OPERATOR_SETUP.md)
- **External-DNS**: See [network/private/external-dns/EXTERNAL_DNS_TAILSCALE_SETUP.md](network/private/external-dns/EXTERNAL_DNS_TAILSCALE_SETUP.md)
- **Cloudflare Tunnel**: See [network/public/cloudflare-tunnel-ingress-controller/CLOUDFLARE_TUNNEL_SETUP.md](network/public/cloudflare-tunnel-ingress-controller/CLOUDFLARE_TUNNEL_SETUP.md)

## Troubleshooting

See [README.md](README.md) for common issues and troubleshooting steps.

