# How-To: Troubleshoot Kubernetes

**Purpose**: Guide AI agents through debugging K3s deployment failures and common cluster issues

**Scope**: Troubleshooting pods, services, ingress, storage, and networking on the homelab K3s cluster

**Overview**: Provides systematic debugging procedures for common K3s issues encountered on
    the homelab cluster. Covers pod failures (CrashLoopBackOff, ImagePullBackOff, OOMKilled),
    networking issues (Traefik routing, Tailscale connectivity, Cloudflare Tunnel), storage
    problems (NFS mounts), and certificate issues (cert-manager, TLS).

**Dependencies**: kubectl configured with cluster access, Tailscale connected to tailnet

**Exports**: Diagnosed and resolved cluster issues

**Related**: BOOTSTRAP.md, README.md, storage/README.md

**Implementation**: Systematic diagnosis with kubectl commands and common fix patterns

**Difficulty**: intermediate

---

## Prerequisites

- **kubectl**: Configured and can reach the cluster (`kubectl get nodes`)
- **Tailscale**: Connected (required for private service access and kubectl via `cluster-node-1:6443`)
- **SSH**: Access to cluster nodes for K3s service-level debugging

## Common Failure Patterns

### Pod Not Starting

**Step 1: Check pod status**
```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
```

**Step 2: Diagnose by status**

| Status | Likely Cause | Fix |
|--------|-------------|-----|
| `ImagePullBackOff` | Wrong image name, missing registry credentials, Harbor unreachable | Check image name, verify `harbor-creds` secret exists in namespace |
| `CrashLoopBackOff` | App crashing on startup | Check logs: `kubectl logs <pod> -n <namespace> --previous` |
| `Pending` | No node can schedule (resource constraints, taints) | Check events: `kubectl get events -n <namespace> --sort-by='.lastTimestamp'` |
| `OOMKilled` | Container exceeds memory limit | Increase memory limit in deployment spec or optimize app |
| `ContainerCreating` (stuck) | Volume mount failure, secret not found | Check events for mount errors, verify secrets/PVCs exist |

### Service Not Accessible

**Step 1: Verify the chain**
```bash
# Pod running?
kubectl get pods -n <namespace>

# Service has endpoints?
kubectl get endpoints <service-name> -n <namespace>

# Ingress configured?
kubectl get ingress -n <namespace>
# or for Traefik IngressRoutes:
kubectl get ingressroute -n <namespace>
```

**Step 2: Test internal connectivity**
```bash
# Port-forward to test the service directly
kubectl port-forward svc/<service-name> -n <namespace> <local-port>:<service-port>
```

**Step 3: Check Traefik**
```bash
# Which Traefik instance?
# Private: traefik-private namespace
# Public: traefik-public namespace

kubectl logs -l app.kubernetes.io/name=traefik -n <traefik-namespace> --tail=50
```

### TLS / Certificate Issues

**Step 1: Check certificate status**
```bash
kubectl get certificates -A
kubectl describe certificate <cert-name> -n <namespace>
```

**Step 2: Check cert-manager logs**
```bash
kubectl logs -l app=cert-manager -n cert-manager --tail=50
```

**Step 3: Common fixes**
- Wildcard cert not propagating: Check that `reflector` is running and annotations are correct
- ACME challenges failing: Verify `CLOUDFLARE_API_TOKEN` has correct permissions
- Private cert (`priv-wildcard-tls`): Verify it exists in the app's namespace

### NFS Storage Issues

**Step 1: Check PVC status**
```bash
kubectl get pvc -n <namespace>
kubectl describe pvc <pvc-name> -n <namespace>
```

**Step 2: Common NFS issues**
- PVC stuck in `Pending`: NFS server unreachable or NFS CSI driver not running
- Mount errors: Check NAS connectivity, verify NFS export paths
- Permission denied: Check NFS squash settings (see `storage/README.md`)

```bash
# Check NFS CSI driver
kubectl get pods -n kube-system | grep nfs

# Test NFS connectivity from a node
ssh main@cluster-node-1 "showmount -e <nas-ip>"
```

### Tailscale Connectivity

**Step 1: Check Tailscale operator**
```bash
kubectl get pods -n tailscale
kubectl logs -l app=tailscale-operator -n tailscale --tail=50
```

**Step 2: Verify Tailscale services**
```bash
# Check if Traefik private has a Tailscale IP
kubectl get svc -n traefik-private
```

### Cloudflare Tunnel Issues

**Step 1: Check tunnel controller**
```bash
kubectl get pods -n cloudflare-tunnel
kubectl logs -l app=cloudflare-tunnel-ingress -n cloudflare-tunnel --tail=50
```

**Step 2: Verify tunnel is connected**
- Check Cloudflare dashboard for tunnel status
- Verify `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in the tunnel secret

## K3s Service-Level Debugging

If kubectl itself is unresponsive:

```bash
# SSH to a control plane node
ssh main@cluster-node-1

# Check K3s service status
sudo systemctl status k3s

# View K3s logs
sudo journalctl -u k3s --tail=100

# Restart K3s if needed
sudo systemctl restart k3s
```

## Kubeconfig Issues

If `kubectl` returns certificate or connection errors after a cluster reset:

```bash
# Fetch fresh kubeconfig
ssh -t main@cluster-node-1 "sudo cat /etc/rancher/k3s/k3s.yaml" > /tmp/k3s-kubeconfig

# Update local kubeconfig (set server to cluster-node-1:6443)
# Copy to ~/.kube/config, replacing the server URL with https://cluster-node-1:6443
```

## Success Criteria

- [ ] Root cause identified
- [ ] Issue resolved or escalated with clear diagnosis
- [ ] No unrelated changes made during troubleshooting
