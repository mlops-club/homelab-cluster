# Tailscale Kubernetes Operator Setup

## Overview

This document describes the setup and configuration of the Tailscale Kubernetes Operator to expose internal Kubernetes services to the Tailscale tailnet, enabling secure access for team members without exposing services to the public internet.

## Why Tailscale Operator?

### Problem Statement

Initially, we configured MetalLB to assign LoadBalancer IPs from the local network range (`192.168.50.200-192.168.50.220`). While this worked for local access, it presented challenges:

1. **Network Isolation**: Services were only accessible from devices on the same physical network
2. **Remote Access Complexity**: Accessing services from remote locations (e.g., team members in different countries) would require:
   - Manual subnet routing configuration on cluster nodes
   - Client-side configuration on each user's device
   - Exposing the entire home network subnet

### Solution: Tailscale Kubernetes Operator

The Tailscale Kubernetes Operator provides:

- **Kubernetes-Native Integration**: Works directly with Kubernetes services via annotations or `loadBalancerClass`
- **Automatic Management**: Creates and manages Tailscale proxies for each exposed service
- **Per-Service Exposure**: Only exposes specific services you choose, not the entire network
- **No Client Configuration**: Team members don't need to enable "accept routes" or configure anything
- **Secure by Default**: Services are only accessible to authenticated Tailscale users in your tailnet
- **Works with Cloudflare Tunnel**: Can be used alongside Cloudflare Tunnel for a hybrid approach (Tailscale for internal services, Cloudflare for public services)

## Prerequisites

- Tailscale account with admin/owner privileges
- Kubernetes cluster (k3s in this case)
- Helm installed
- `kubectl` configured to access your cluster

## Installation Steps

### 1. Create OAuth Credentials

1. Navigate to the Tailscale admin console: https://login.tailscale.com/admin/settings/oauth
2. Create a new OAuth client with the following **write** scopes:
   - `Devices Core` (Write)
   - `Auth Keys` (Write)
   - `Services` (Write)
3. Assign the tag: `tag:k8s-operator`
4. Save the **Client ID** and **Client Secret** for later use

### 2. Configure Tailnet ACL Policy

1. Navigate to: https://login.tailscale.com/admin/acls
2. Add the following to your ACL policy file:

```json
{
  "tagOwners": {
    "tag:k8s-operator": [],
    "tag:k8s": ["tag:k8s-operator"]
  }
}
```

This configuration allows the operator to manage devices tagged with `tag:k8s`.

3. Save the policy file

### 3. Install Helm (if not already installed)

```bash
# On macOS
brew install helm

# Or download from https://helm.sh/docs/intro/install/
```

### 4. Install Tailscale Operator

Add the Tailscale Helm repository:

```bash
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update
```

Install the operator (replace `<clientId>` and `<clientSecret>` with your actual OAuth credentials):

```bash
helm upgrade --install tailscale-operator tailscale/tailscale-operator \
  --namespace tailscale \
  --create-namespace \
  --set-string oauth.clientId=<clientId> \
  --set-string oauth.clientSecret=<clientSecret> \
  --wait
```

### 5. Verify Installation

Check that the operator pod is running:

```bash
kubectl get pods -n tailscale
```

You should see a pod named `operator-<identifier>` with status `Running`.

Verify in Tailscale admin console that a new device tagged with `tag:k8s-operator` has joined your tailnet.

## Configuring Services

### Service Configuration

To expose a Kubernetes service via Tailscale, update the service manifest:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx
  labels:
    app: nginx
  annotations:
    tailscale.com/expose: "true"
spec:
  type: LoadBalancer
  loadBalancerClass: tailscale
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
    name: http
  selector:
    app: nginx
```

Key changes:
- **Annotation**: `tailscale.com/expose: "true"` - Explicitly tells Tailscale to expose this service
- **loadBalancerClass**: `tailscale` - Uses Tailscale operator instead of MetalLB

### Applying the Configuration

If updating an existing service that was using MetalLB, you need to delete and recreate it (since `loadBalancerClass` is immutable):

```bash
# Delete the existing service
kubectl delete svc nginx

# Apply the updated manifest
kubectl apply -f nginx-deployment/manifest.yaml
```

### Verify Service Exposure

Check the service status:

```bash
kubectl get svc nginx
```

You should see a Tailscale IP (like `100.x.x.x`) in the `EXTERNAL-IP` column instead of a local network IP.

## Accessing Services

Once a service is exposed via Tailscale:

1. **Team members** connected to your tailnet can access the service using the Tailscale IP
2. **No additional configuration** is needed on client devices
3. **MagicDNS** can be used for friendly domain names (e.g., `nginx.tailnet-name.ts.net`)

Example access:
```
http://100.x.x.x
```

## Architecture: Tailscale + Cloudflare Tunnel

This setup supports a hybrid approach:

- **Tailscale Operator**: For internal/admin services (Grafana, Prometheus, Kubernetes dashboard)
- **Cloudflare Tunnel**: For public-facing web applications

Both can coexist in the same cluster without conflicts, allowing you to:
- Keep internal services private and secure
- Expose public services with Cloudflare's security features (DDoS protection, WAF, CDN)

## Troubleshooting

### Service Not Getting Tailscale IP

1. Check operator pod status:
   ```bash
   kubectl get pods -n tailscale
   kubectl logs -n tailscale -l app=tailscale-operator
   ```

2. Verify OAuth credentials are correct
3. Check Tailscale admin console for the operator device
4. Ensure ACL policy has the correct tag configuration

### Cannot Access Service from Tailnet

1. Verify the service has a Tailscale IP assigned
2. Check that you're connected to the correct tailnet
3. Verify ACL policies allow access
4. Check service endpoints:
   ```bash
   kubectl get endpoints nginx
   ```

## References

- [Tailscale Kubernetes Operator Documentation](https://tailscale.com/kb/1236/kubernetes-operator)
- [Tailscale Operator Troubleshooting](https://tailscale.com/kb/1446/kubernetes-operator-troubleshooting)
- [Tailscale ACL Policy Documentation](https://tailscale.com/kb/1018/acls)

## Summary

The Tailscale Kubernetes Operator provides a clean, Kubernetes-native way to expose internal services to your team members via Tailscale. It eliminates the need for manual subnet routing configuration and provides better security isolation compared to exposing entire network subnets. Combined with Cloudflare Tunnel for public services, this setup provides a comprehensive solution for both internal and external service exposure.

