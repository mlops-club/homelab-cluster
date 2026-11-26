# How-To: Deploy a New App

**Purpose**: Guide AI agents through deploying a new application to the homelab K3s cluster

**Scope**: Application deployment following the established namespace-per-app pattern with Traefik ingress

**Overview**: Walks through the process of deploying a new application to the cluster. Covers creating the
    namespace, deployment, service, and ingress resources following the established pattern used by
    existing apps (come-follow-me-app, seminary-feedback). Supports both public (Cloudflare Tunnel)
    and private (Tailscale) exposure paths.

**Dependencies**: Running K3s cluster, Harbor registry (for private images), Traefik ingress controllers

**Exports**: A fully deployed and accessible application on the cluster

**Related**: BOOTSTRAP.md, network/private/README.md, network/public/README.md

**Implementation**: Single-manifest deployment with namespace, deployment, service, and ingress

**Difficulty**: intermediate

---

## Prerequisites

- **Cluster**: K3s cluster is running and `kubectl` is configured
- **Networking**: Private and/or public network stacks are deployed
- **Image**: Container image is available (Docker Hub, Harbor at `cr.priv.mlops-club.org`, or other registry)
  and is multi-arch (`linux/amd64` + `linux/arm64`), or the Deployment pins `kubernetes.io/arch` (see
  Container Image Rules in `.ai/ai-rules.md`)
- **DNS**: Domain is configured (mlops-club.org for public, priv.mlops-club.org for private)

## Steps

### Step 1: Choose Exposure Path

Determine how the app should be accessible:

| Path | Domain Pattern | Ingress Class | TLS | Access |
|------|---------------|---------------|-----|--------|
| **Public** | `<app>.mlops-club.org` | `traefik-public` | Cloudflare handles edge TLS | Internet |
| **Private** | `<app>.priv.mlops-club.org` | `traefik-private` | `priv-wildcard-tls` cert, served by default (no `secretName`) | Tailscale only |

### Step 2: Create App Directory

```bash
mkdir -p apps/<app-name>/
```

### Step 3: Create the Manifest

Create `apps/<app-name>/manifest.yaml` with all resources in a single file, separated by `---`:

**For Public Apps** (via Cloudflare Tunnel):

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: <app-name>
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <app-name>
  namespace: <app-name>
  labels:
    app: <app-name>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <app-name>
  template:
    metadata:
      labels:
        app: <app-name>
    spec:
      containers:
      - name: <app-name>
        image: <image>:<tag>
        ports:
        - containerPort: <port>
          name: http
---
apiVersion: v1
kind: Service
metadata:
  name: <app-name>
  namespace: <app-name>
  labels:
    app: <app-name>
spec:
  type: ClusterIP
  ports:
  - name: http
    port: <port>
    targetPort: <port>
  selector:
    app: <app-name>
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <app-name>
  namespace: <app-name>
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  ingressClassName: traefik-public
  rules:
  - host: <app-name>.mlops-club.org
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: <app-name>
            port:
              number: <port>
```

**For Private Apps** (via Tailscale): Use `ingressClassName: traefik-private` and host `<app-name>.priv.mlops-club.org`. Add a `tls` block that lists the host and names no secret; traefik-private serves the wildcard `priv-wildcard-tls` as its default certificate, so nothing is copied into the app namespace:

```yaml
  tls:
  - hosts:
    - <app-name>.priv.mlops-club.org
```

Traefik objects such as `Middleware` or `IngressRoute` can live in the app namespace but must carry the label `traefik.mlops-club.org/instance: private` (or `public`), or that Traefik ignores them.

### Step 4: Create Deploy Script

Create `apps/<app-name>/deploy.sh`:

```bash
#!/bin/bash
# deploy.sh
# Purpose: Deploy <app-name> to the K3s cluster
# Usage: ./apps/<app-name>/deploy.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl apply -f "${SCRIPT_DIR}/manifest.yaml"
```

Make it executable:
```bash
chmod +x apps/<app-name>/deploy.sh
```

### Step 5: Build and Check a Multi-Arch Image

The cluster has amd64 NUCs and an arm64 node (`cluster-node-5`). Build images you own for both:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t cr.priv.mlops-club.org/<app-name>/app:<tag> --push .
docker buildx imagetools inspect cr.priv.mlops-club.org/<app-name>/app:<tag>   # lists both platforms
```

For a third-party image that has only one architecture, add to the pod spec:

```yaml
nodeSelector:
  kubernetes.io/arch: amd64   # <image> publishes amd64 only
```

### Step 5b: Handle Private Registry Images (if needed)

If using Harbor (`cr.priv.mlops-club.org`):

1. Add `imagePullSecrets` to the deployment spec:
   ```yaml
   spec:
     imagePullSecrets:
     - name: harbor-creds
   ```

2. Ensure the Harbor credentials secret exists in the app namespace:
   ```bash
   kubectl create secret docker-registry harbor-creds \
     --namespace <app-name> \
     --docker-server=cr.priv.mlops-club.org \
     --docker-username=<user> \
     --docker-password=<password>
   ```

### Step 6: Deploy

```bash
./apps/<app-name>/deploy.sh
```

### Step 7: Verify

```bash
# Check pod status
kubectl get pods -n <app-name>

# Check service
kubectl get svc -n <app-name>

# Check ingress
kubectl get ingress -n <app-name>

# Watch logs
kubectl logs -f -l app=<app-name> -n <app-name>

# Test access (public)
curl -s https://<app-name>.mlops-club.org

# Test access (private, requires Tailscale)
curl -s https://<app-name>.priv.mlops-club.org
```

## Success Criteria

- [ ] App directory exists at `apps/<app-name>/`
- [ ] manifest.yaml contains Namespace, Deployment, Service, and Ingress
- [ ] deploy.sh is executable and applies the manifest
- [ ] Image lists both `linux/amd64` and `linux/arm64`, or the Deployment pins `kubernetes.io/arch`
- [ ] Pod is running and healthy
- [ ] Service is accessible via the chosen domain
