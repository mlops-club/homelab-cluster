# MLOps Club Kubernetes Cluster

## Infrastructure Dependency Graph

All Helm releases are managed by [`helmfile.yaml.gotmpl`](./helmfile.yaml.gotmpl). The graph below shows release dependencies, presync inputs, and postsync outputs.

<!-- HELMFILE-GRAPH-START -->
<!-- Update this diagram when adding/removing releases or modifying hooks in helmfile.yaml.gotmpl -->

```mermaid
graph TD
    %% ── Color legend ──────────────────────────────────────────────
    %% Blue  = Helm release (the deployable unit helmfile manages)
    %% Green = Resource created by a hook (not tracked by Helm)
    %% Shapes: rounded rect = release, hexagon = hook-created resource

    %% ── STORAGE ───────────────────────────────────────────────────
    subgraph storage [Storage]
        NFS[csi-driver-nfs<br/><sub>nfs-system · v4.12.1</sub>]:::release
        SC{{StorageClass: nas-nfs}}:::hook
        NFS -- postsync --> SC
    end

    %% ── GPU ──────────────────────────────────────────────────────
    subgraph gpu [GPU · gpu-operator]
        GPU_OP[gpu-operator<br/><sub>v26.3.2</sub>]:::release
    end

    %% ── OBSERVABILITY ────────────────────────────────────────────
    subgraph obs [Observability · opentelemetry-*]
        BS_SEC{{Secret:<br/>betterstack-sandbox-ingest-token}}:::hook
        OTEL_OP[opentelemetry-operator<br/><sub>v0.115.0</sub>]:::release
        OTEL_COL{{OpenTelemetryCollector:<br/>gateway + RBAC}}:::hook

        BS_SEC -- presync --> OTEL_OP
        OTEL_OP -- postsync --> OTEL_COL
    end

    %% ── PRIVATE NETWORK ──────────────────────────────────────────
    subgraph private [Private Network · traefik-private]
        CM_CRD{{cert-manager CRDs<br/><sub>6 CRDs · v1.19.2</sub>}}:::hook
        CM[cert-manager<br/><sub>v1.19.2</sub>]:::release
        CF_SEC{{Secret: cloudflare-api-token}}:::hook
        CI{{ClusterIssuer:<br/>letsencrypt-cloudflare}}:::hook

        CM_CRD -- presync --> CM
        CM -- postsync --> CF_SEC
        CM -- postsync --> CI

        REF[reflector<br/><sub>v9.1.45</sub>]:::release
        TS[tailscale-operator<br/><sub>v1.92.5</sub>]:::release
        EDNS[external-dns<br/><sub>v1.20.0</sub>]:::release

        TK_CRD{{Traefik CRDs<br/><sub>33 CRDs · v38.0.2</sub>}}:::hook
        CERT_PRIV{{Certificate:<br/>*.priv.mlops-club.org}}:::hook
        TP[traefik-private<br/><sub>v38.0.2</sub>]:::release

        TK_CRD -- presync --> TP
        CERT_PRIV -- presync --> TP
    end

    %% ── PUBLIC NETWORK ───────────────────────────────────────────
    subgraph public [Public Network · traefik-public]
        CFT[cloudflare-tunnel<br/><sub>v0.0.21</sub>]:::release
        TPUB[traefik-public<br/><sub>v38.0.2</sub>]:::release
        CERT_PUB{{Certificate:<br/>*.mlops-club.org}}:::hook
        ING{{Ingress:<br/>traefik-public-catchall}}:::hook

        TPUB -- postsync --> CERT_PUB
        TPUB -- postsync --> ING
    end

    %% ── IMAGE REGISTRY ───────────────────────────────────────────
    subgraph registry [Image Registry · image-registry]
        HAR_SEC{{Secret: harbor-admin}}:::hook
        HAR[harbor<br/><sub>v1.18.1</sub>]:::release
        HAR_SEC -- presync --> HAR
    end

    %% ── INTER-RELEASE DEPENDENCIES (needs) ───────────────────────
    CM --> TP
    REF --> TP
    TS --> TP
    EDNS --> TP

    CF_SEC -.-> EDNS

    CFT --> TPUB
    CM --> TPUB

    NFS --> HAR
    TP --> HAR

    %% OpenTelemetry Operator needs cert-manager (webhook TLS) and
    %% gpu-operator (provides dcgm-exporter Service to scrape).
    CM --> OTEL_OP
    GPU_OP --> OTEL_OP

    %% ── STYLES ───────────────────────────────────────────────────
    classDef release fill:#dbeafe,stroke:#2563eb,color:#1e3a5f
    classDef hook fill:#d1fae5,stroke:#059669,color:#064e3b

    style storage fill:#f8fafc,stroke:#cbd5e1,color:#334155
    style gpu fill:#f8fafc,stroke:#cbd5e1,color:#334155
    style obs fill:#f8fafc,stroke:#cbd5e1,color:#334155
    style private fill:#f8fafc,stroke:#cbd5e1,color:#334155
    style public fill:#f8fafc,stroke:#cbd5e1,color:#334155
    style registry fill:#f8fafc,stroke:#cbd5e1,color:#334155
```

**Legend**: Blue = Helm release managed by helmfile · Green = resource created by a presync/postsync hook · Solid arrow = `needs` dependency or hook relationship · Dotted arrow = implicit dependency (secret used by another release)

<!-- HELMFILE-GRAPH-END -->

## Quick Start (set up cluster from scratch)

Prerequisites
1. fill out `.env.example` and rename it to `.env`
2. install tailscale and join the tailnet

```bash
cd ./k3s-ansible
./run deploy
```

Now copy the kubeconfig file

```bash
ssh -t main@cluster-node-1 "sudo cat /etc/rancher/k3s/k3s.yaml" > k3s-ansible/kubeconfig
# ^^^ prints it to the terminal, then copy and
pbpaste > ~/.kube/config
# ^^^ be sure to set server to https://cluster-node-1:6443
```

## K3s Deployment with Ansible

- [`k3s-ansible/`](./k3s-ansible/). This was taken from [this git repo](https://github.com/timothystewart6/k3s-ansible) NO modifications were made, except:
  - [./k3s-ansible/inventory/cluster/group_vars/all.yml](./k3s-ansible/inventory/cluster/group_vars/all.yml)
  - [./k3s-ansible/inventory/cluster/hosts.ini](./k3s-ansible/inventory/cluster/hosts.ini)
  - Deploy with `bash ./k3s-ansible/run deploy`.
  - Teardown with `bash ./k3s-ansible/run reset`.

Note, the `run` script uses `uv` and a `pyproject.toml` file which we added to make dependency management cleaner.

In [`all.yml`](./k3s-ansible/inventory/cluster/group_vars/all.yml), we only changed a few values from default:
- `system_timezone: America/Denver`
- `flannel_iface: enp1s0` Because the NUCs use that interface instead of `eth0`.
- `metal_lb_ip_range: 192.168.50.200-192.168.50.220` Because the NUCs are on a LAN with IPs in `192.168.50.(up to 199)` and the IPs assigned to pods by metallb must not overlap with those.

![](./assets/cloudflare-tunnel-dns-records.png)

## TLS/SSL with Traefik

Cloudflare can manage a single wildcard TLS cert for us.

> So we don't have to go through the pain of LetsEncrypt rate limits when we accidentally try to issue a cert more than 5 times in a day.

![](./assets/origin-cert.png)

![](./assets/sans.png)

## Common issues

### Reaching the control plane

Set this line and make sure tailscale is enabled

```yaml
# ~/.kube/config
clusters:
  cluster:
    server: https://cluster-node-1:6443
```

### TLS errors with kubectl

```bash
$ kubectl get nodes -o wide
Error from server (BadRequest): Unable to list "/v1, Resource=nodes": the server rejected our request for an unknown reason (get nodes)
```

Cause: When `./run reset` is run, new x509 certs are generated on the cluster nodes, which means the certs in `~/.kube/config` are out of date.

Fix: run

```bash
ssh -t main@cluster-node-1 "sudo cat /etc/rancher/k3s/k3s.yaml" > k3s-ansible/kubeconfig
```

then copy the resulting kubeconfig to the clipboard, and paste it to the right location with `pbpaste > ~/.kube/config`.

## Appendix: Traefik HTTPS Configuration Comparison

When using Traefik for HTTPS termination, services can be exposed either internally (via Tailscale) or externally (via Cloudflare Tunnel). The following table compares the key differences:

| Aspect | Internal HTTPS (private) | External HTTPS (public) |
|--------|--------------------------|-------------------------|
| **Ingress Class** | `traefik-private` | `traefik-pub` |
| **TLS Secret** | `priv-wildcard-tls` (wildcard `*.priv.mlops-club.org`) | `cloudflare-origin-cert` (or ACME) |
| **External-DNS Annotation** | ✅ Required (points to Traefik's Tailscale IP) | ❌ Not needed |
| **Traefik Exposure** | Via Tailscale LoadBalancer | Via Cloudflare Tunnel Ingress |
| **DNS Management** | External-DNS creates A record | Cloudflare Tunnel creates DNS |
| **Access** | Tailscale network only | Public internet |

Both configurations use the same Traefik Ingress class and TLS configuration. The key difference is how Traefik itself is exposed (Tailscale LoadBalancer vs Cloudflare Tunnel) and how DNS records are managed.

## Cloudflare tunnel + Traefik routing

We use `*.mlops-club.org` (single-level wildcard) to leverage Cloudflare's free Universal SSL certificates. The Cloudflare Tunnel Ingress Controller is configured to route all `*.mlops-club.org` subdomains that don't have explicit DNS records to Traefik. Traefik then routes traffic to the appropriate services based on host headers.

**Architecture:**
- **Cloudflare Tunnel Ingress**: Configured with `*.mlops-club.org` host rule, routes all matching subdomains → Traefik (port 80, HTTP)
- **Traefik**: Routes based on host header (e.g., `whoami.mlops-club.org` → whoami service) using `web` entrypoint (HTTP)
- **TLS**:
  - Edge: Cloudflare handles TLS termination (free Universal SSL for `*.mlops-club.org`)
  - Origin: No TLS needed - Cloudflare Tunnel connects to Traefik via HTTP (port 80)

**Configuration:**
- Cloudflare Tunnel Ingress: [`network/public/traefik/traefik-ingress.yaml`](./network/public/traefik/traefik-ingress.yaml) - Routes `*.mlops-club.org` to Traefik on port 80
- Services: Create standard Kubernetes Ingress resources with `ingressClassName: traefik-public` and `router.entrypoints: web` (no TLS needed)
- Example: [`whoami-deployment/whoami-public.yaml`](./whoami-deployment/whoami-public.yaml)

**Why `*.mlops-club.org` instead of `*.lab.mlops-club.org`?**
- Cloudflare's free Universal SSL only covers single-level wildcards (`*.mlops-club.org`)
- Multi-level wildcards (`*.lab.mlops-club.org`) require paid "Total TLS" or "Advanced Certificate Manager" ($10/month)
- Single-level wildcard works perfectly for our use case: `app1.mlops-club.org`, `app2.mlops-club.org`, etc.
