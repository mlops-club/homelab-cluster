# Public Network Components

This directory contains all components for exposing public-facing services via Cloudflare Tunnel and Traefik.

## Overview

The public network stack provides secure, public access to services through:
- **Cloudflare Tunnel**: Encrypted tunnel from Cloudflare edge to your cluster
- **Traefik**: Reverse proxy and ingress controller for routing
- **TLS Termination**: Handled at Cloudflare edge only (Traefik receives HTTP traffic)

## Architecture

### Resource Diagram

```mermaid
graph TB
    subgraph "traefik-public namespace"
        CTIC[Cloudflare Tunnel<br/>Ingress Controller]
        TP[Traefik Public<br/>Service]
    end
    
    subgraph "whoami-external namespace"
        APP1[whoami Service]
        ING1[Ingress<br/>whoami.mlops-club.org]
    end
    
    subgraph "Other namespaces"
        APP2[App Service 1]
        APP3[App Service 2]
    end
    
    CTIC -->|Creates Tunnel Routes| TP
    TP -->|Routes to| ING1
    TP -->|Routes to| APP2
    TP -->|Routes to| APP3
    ING1 -->|Routes to| APP1
    
    style CTIC fill:#e1f5ff
    style TP fill:#e1f5ff
    style APP1 fill:#fff4e1
    style APP2 fill:#fff4e1
    style APP3 fill:#fff4e1
    style ING1 fill:#e8f5e9
```

### Network Diagram

```mermaid
graph LR
    subgraph "Internet"
        Client[Client Browser]
    end
    
    subgraph "Cloudflare Edge"
        CFEdge[Cloudflare Edge<br/>TLS Termination<br/>WAF, DDoS Protection]
    end
    
    subgraph "Kubernetes Cluster"
        subgraph "traefik-public namespace"
            Tunnel[Cloudflare Tunnel<br/>cloudflared]
            Traefik[Traefik Public<br/>Port 80<br/>HTTP Routing]
        end
        
        subgraph "whoami-external namespace"
            Ingress[Ingress<br/>whoami.mlops-club.org]
            Service[whoami Service]
        end
    end
    
    Client -->|HTTPS<br/>whoami.mlops-club.org| CFEdge
    CFEdge -->|HTTP<br/>Port 80| Tunnel
    Tunnel -->|HTTP<br/>Port 80| Traefik
    Traefik -->|HTTP| Ingress
    Ingress -->|HTTP| Service
    
    style Client fill:#e3f2fd
    style CFEdge fill:#fff3e0
    style Tunnel fill:#e1f5ff
    style Traefik fill:#e1f5ff
    style Ingress fill:#e8f5e9
    style Service fill:#e8f5e9
```

### DNS Configuration

#### DNS Records

| Record Type | Hostname | Target | Source | Managed By |
|-------------|----------|--------|--------|------------|
| **Tunnel Route** | `*.mlops-club.org` | `k3s-tunnel` → Traefik service (ClusterIP) `http://traefik-public.traefik-public.svc.cluster.local:80` | Cloudflare Tunnel Ingress Controller | Cloudflare Tunnel |
| **Tunnel Route** | `traefik.mlops-club.org` | `k3s-tunnel` → Traefik service (ClusterIP) `http://traefik-public.traefik-public.svc.cluster.local:80` | [`traefik/traefik-ingress.yaml`](traefik/traefik-ingress.yaml) | Cloudflare Tunnel |

**How it works:**
1. Cloudflare Tunnel Ingress Controller watches for Ingress resources with `ingressClassName: cloudflare-tunnel`
2. Creates tunnel routes in Cloudflare pointing to the backend service
3. No DNS A records needed - Cloudflare Tunnel handles routing internally
4. All `*.mlops-club.org` subdomains are routed to Traefik via the tunnel

### Network Flow Diagram

```mermaid
sequenceDiagram
    participant Client
    participant CFEdge as Cloudflare Edge<br/>(TLS Termination)
    participant Tunnel as Cloudflare Tunnel<br/>(cloudflared)
    participant Traefik as Traefik Public
    participant Service as Application Service
    
    Note over Client,CFEdge: Connection 1: Client → Cloudflare
    Client->>CFEdge: HTTPS Request<br/>(whoami.mlops-club.org)
    Note over CFEdge: Edge Certificate<br/>(Auto-provisioned by Cloudflare)
    CFEdge->>CFEdge: Terminates TLS<br/>(WAF, DDoS protection)
    
    Note over CFEdge,Tunnel: Connection 2: Cloudflare → Traefik
    CFEdge->>Tunnel: Forward via encrypted tunnel
    Tunnel->>Traefik: HTTP Request<br/>(Port 80)
    Note over Traefik: Routes by Host header<br/>(whoami.mlops-club.org)
    Traefik->>Service: HTTP Request<br/>(Internal routing)
    Service-->>Traefik: HTTP Response
    Traefik-->>Tunnel: HTTP Response
    Tunnel-->>CFEdge: Forward response
    CFEdge-->>Client: HTTPS Response
```

### Certificate Management Flow

**Note**: In the current configuration, TLS termination only happens at Cloudflare edge. Traefik receives HTTP traffic on port 80. The certificate management flow below shows how certificates *could* be managed if TLS termination at Traefik were enabled, but it's not currently used in this setup.

```mermaid
sequenceDiagram
    participant CM as cert-manager<br/>(Private Stack)
    participant LE as Let's Encrypt
    participant CF as Cloudflare API
    participant K8s as Kubernetes<br/>(Secret)
    participant Traefik as Traefik Public<br/>(Not Currently Used)
    
    Note over CM,LE: Certificate Request
    CM->>LE: Request Certificate<br/>(*.mlops-club.org)
    LE->>CM: DNS-01 Challenge
    
    Note over CM,CF: DNS Challenge
    CM->>CF: Create TXT Record<br/>(_acme-challenge.mlops-club.org)
    CF-->>CM: TXT Record Created
    CM->>LE: Verify Challenge
    LE->>CF: Verify TXT Record
    CF-->>LE: Challenge Valid
    
    Note over LE,K8s: Certificate Issuance
    LE-->>CM: Certificate Issued
    CM->>K8s: Create Secret<br/>(mlops-wildcard-tls)
    Note over K8s: Secret available but<br/>not used in current setup
```

## Components

| Component | Namespace | Purpose | Configuration | Documentation |
|-----------|-----------|---------|---------------|---------------|
| **Cloudflare Tunnel Ingress Controller** | `traefik-public` | Automatically creates Cloudflare Tunnel routes for Kubernetes Ingress resources | [`cloudflare-tunnel-ingress-controller/values.yaml`](cloudflare-tunnel-ingress-controller/values.yaml) | [`cloudflare-tunnel-ingress-controller/CLOUDFLARE_TUNNEL_SETUP.md`](cloudflare-tunnel-ingress-controller/CLOUDFLARE_TUNNEL_SETUP.md) |
| **Traefik Public** | `traefik-public` | Reverse proxy and ingress controller for routing requests to services | [`traefik/values.yaml`](traefik/values.yaml), [`traefik/traefik-ingress.yaml`](traefik/traefik-ingress.yaml) | [`traefik/TLS_ARCHITECTURE.md`](traefik/TLS_ARCHITECTURE.md), [`traefik/DNS_SETUP.md`](traefik/DNS_SETUP.md) |

## Installation

### Quick Start

```bash
# Install all public components
./network/public/helm-install.sh
```

### Manual Installation

```bash
# 1. Install Cloudflare Tunnel Ingress Controller
./network/public/cloudflare-tunnel-ingress-controller/helm-install.sh

# 2. Install Traefik Public
./network/public/traefik/helm-install.sh
```

### Uninstallation

```bash
# Uninstall all public components
./network/public/helm-uninstall.sh
```

## Example Services

### Deploy Example whoami Service

```bash
# Deploy whoami service in whoami-external namespace
./network/public/examples/deploy-whoami-external.sh
```

The service will be accessible at: `https://whoami.mlops-club.org`

### Example Ingress Configuration

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  namespace: my-namespace
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik-public
  tls:
  - hosts:
    - my-app.mlops-club.org
    secretName: mlops-wildcard-tls
  rules:
  - host: my-app.mlops-club.org
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: my-app
            port:
              number: 80
```

**Note**: No Cloudflare Tunnel Ingress annotation needed! The catch-all Ingress in `traefik-public` namespace routes all `*.mlops-club.org` traffic to Traefik, which then routes based on the Host header.

## TLS Certificates

### Single-Level TLS Architecture

**Cloudflare Edge Certificate** (Automatic)
- Managed by Cloudflare
- Encrypts Client → Cloudflare connection
- Auto-provisioned when domain is added to Cloudflare
- TLS is terminated at Cloudflare edge only

**Note**: In the current configuration, Cloudflare Tunnel connects to Traefik via HTTP (port 80). TLS termination happens only at the Cloudflare edge. Traefik receives unencrypted HTTP traffic internally.

See `traefik/TLS_ARCHITECTURE.md` for detailed explanation (note: that document describes a two-level TLS setup, but the current configuration uses single-level TLS at Cloudflare edge only).

## Troubleshooting

### Service Not Accessible

1. **Check Cloudflare Tunnel status**:
   ```bash
   kubectl get pods -n traefik-public
   kubectl logs -n traefik-public -l app=cloudflare-tunnel-ingress-controller
   ```

2. **Check Traefik status**:
   ```bash
   kubectl get pods -n traefik-public
   kubectl get ingress -n traefik-public
   ```

3. **Verify Ingress configuration**:
   ```bash
   kubectl describe ingress <ingress-name> -n <namespace>
   ```

4. **Check Cloudflare Dashboard**:
   - SSL/TLS → Edge Certificates (should show active certificate)
   - SSL/TLS mode should be "Full" or "Full (strict)"

### TLS Certificate Issues

- **Edge certificate not ready**: Wait 5-15 minutes after adding domain to Cloudflare
- **Origin certificate missing**: Ensure cert-manager is installed and `mlops-wildcard-tls` secret exists

## Related Documentation

- `traefik/TLS_ARCHITECTURE.md` - Detailed TLS certificate architecture
- `traefik/DNS_SETUP.md` - DNS configuration guide
- `traefik/FREE_SSL_SOLUTION.md` - SSL/TLS setup guide
- `cloudflare-tunnel-ingress-controller/CLOUDFLARE_TUNNEL_SETUP.md` - Tunnel setup guide

## Directory Structure

```
public/
├── cloudflare-tunnel-ingress-controller/
│   ├── helm-install.sh
│   ├── values.yaml
│   └── CLOUDFLARE_TUNNEL_SETUP.md
├── traefik/
│   ├── helm-install.sh
│   ├── values.yaml
│   ├── traefik-ingress.yaml
│   └── [documentation files]
├── examples/
│   ├── deploy-whoami-external.sh
│   └── whoami-external.yaml
├── helm-install.sh
├── helm-uninstall.sh
└── README.md (this file)
```

