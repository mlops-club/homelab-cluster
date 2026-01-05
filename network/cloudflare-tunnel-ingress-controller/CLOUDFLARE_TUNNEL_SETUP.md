# Cloudflare Tunnel Ingress Controller Setup

## Overview

This document describes the setup and configuration of the Cloudflare Tunnel Ingress Controller to expose Kubernetes services to the public internet securely using Cloudflare Tunnels. This provides a modern alternative to traditional load balancers and works seamlessly alongside the Tailscale Operator for a hybrid approach to service exposure.

## Why Cloudflare Tunnel?

### Problem Statement

Traditional approaches to exposing Kubernetes services to the internet have limitations:

1. **Load Balancer Requirements**: Requires external IP addresses and often expensive cloud load balancers
2. **Network Configuration**: May require opening firewall ports and managing ingress IPs
3. **Security Concerns**: Direct exposure of services to the internet without built-in DDoS protection
4. **Cost**: Cloud load balancers can be expensive for small deployments

### Solution: Cloudflare Tunnel Ingress Controller

The Cloudflare Tunnel Ingress Controller provides:

- **Kubernetes-Native Integration**: Works with standard Kubernetes Ingress resources
- **Automatic Tunnel Management**: Creates and manages Cloudflare Tunnels automatically
- **Zero Trust Security**: Services are tunneled through Cloudflare's network, no open ports required
- **Built-in DDoS Protection**: Leverages Cloudflare's global network and security features
- **Automatic DNS Management**: Creates DNS records automatically for your services
- **Cost Effective**: Free tier available, no need for expensive load balancers
- **Works with Tailscale**: Can coexist with Tailscale Operator for hybrid access (Tailscale for internal, Cloudflare for public)

## Prerequisites

- Cloudflare account with a domain configured on Cloudflare DNS
- Kubernetes cluster (k3s in this case)
- Helm installed
- `kubectl` configured to access your cluster
- Cloudflare API token with appropriate permissions

## Installation Steps

### 1. Create Cloudflare API Token

1. Navigate to the Cloudflare API tokens page: https://dash.cloudflare.com/profile/api-tokens
2. Click "Create Token"
3. Use the quick template URL to create a token with required permissions:
   ```
   https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=[{"key":"zone","type":"read"},{"key":"dns","type":"edit"},{"key":"argotunnel","type":"edit"}]&name=Cloudflare%20Tunnel%20Ingress%20Controller&accountId=*&zoneId=all
   ```
4. Required permissions:
   - `Zone:Zone:Read` - Read zone information
   - `Zone:DNS:Edit` - Create and manage DNS records
   - `Account:Cloudflare Tunnel:Edit` - Create and manage tunnels
5. Save the **API Token** for later use

### 2. Get Cloudflare Account ID

1. Navigate to your Cloudflare dashboard: https://dash.cloudflare.com/
2. Select your account
3. Copy the **Account ID** from the right sidebar
4. Alternatively, follow the [official guide](https://developers.cloudflare.com/fundamentals/get-started/basic-tasks/find-account-and-zone-ids/)

### 3. Add Helm Repository

Add the Cloudflare Tunnel Ingress Controller Helm repository:

```bash
helm repo add strrl.dev https://helm.strrl.dev
helm repo update
```

### 4. Install Cloudflare Tunnel Ingress Controller

Install the controller using Helm with your credentials:

```bash
helm upgrade --install --wait \
  -n cloudflare-tunnel-ingress-controller --create-namespace \
  cloudflare-tunnel-ingress-controller \
  strrl.dev/cloudflare-tunnel-ingress-controller \
  --set=cloudflare.apiToken="<your-cloudflare-api-token>",cloudflare.accountId="<your-cloudflare-account-id>",cloudflare.tunnelName="<your-favorite-tunnel-name>"
```

Replace:
- `<your-cloudflare-api-token>` with your API token from step 1
- `<your-cloudflare-account-id>` with your Account ID from step 2
- `<your-favorite-tunnel-name>` with your preferred tunnel name (e.g., `k3s-tunnel`)

**Note**: If the tunnel doesn't exist, the controller will create it automatically.

### 5. Verify Installation

Check that the controller pod is running:

```bash
kubectl -n cloudflare-tunnel-ingress-controller get pods -l app.kubernetes.io/name=cloudflare-tunnel-ingress-controller
```

You should see a pod with status `Running`.

Verify in Cloudflare Dashboard:
- Go to Zero Trust → Networks → Tunnels
- You should see your tunnel listed and active

## Configuring Services

### Service Configuration

To expose a Kubernetes service via Cloudflare Tunnel, you need:

1. **Deployment**: Your application deployment
2. **Service**: A ClusterIP service (standard for Ingress-based routing)
3. **Ingress**: An Ingress resource with `ingressClassName: cloudflare-tunnel`

### Example Manifest

Here's a complete example for exposing an nginx service:

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-cloudflare
  labels:
    app: nginx-cloudflare
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx-cloudflare
  template:
    metadata:
      labels:
        app: nginx-cloudflare
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
          name: http
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-cloudflare
  labels:
    app: nginx-cloudflare
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
    name: http
  selector:
    app: nginx-cloudflare
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nginx-cloudflare-ingress
spec:
  ingressClassName: cloudflare-tunnel
  rules:
  - host: nginx.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nginx-cloudflare
            port:
              number: 80
```

### Key Configuration Points

1. **Service Type**: Use `ClusterIP` (not `LoadBalancer`)
   - Cloudflare Tunnel routes through Ingress, not LoadBalancer services
   - ClusterIP is the standard and most efficient for Ingress-based routing

2. **Ingress Class**: Must use `ingressClassName: cloudflare-tunnel`
   - This tells the controller to handle this Ingress resource

3. **Host**: Replace `nginx.yourdomain.com` with your actual domain
   - The domain must be managed by Cloudflare DNS
   - The controller will automatically create the DNS record

### Applying the Configuration

```bash
kubectl apply -f nginx-deployment/manifest-cloudflare.yaml
```

## How It Works

1. **Ingress Creation**: When you create an Ingress resource with `ingressClassName: cloudflare-tunnel`, the controller detects it
2. **Tunnel Management**: The controller ensures a Cloudflare Tunnel exists (creates it if needed)
3. **DNS Record Creation**: Automatically creates DNS records pointing to the tunnel
4. **Traffic Routing**: 
   - Internet → Cloudflare Edge → Cloudflare Tunnel → Kubernetes Ingress → Service → Pods
5. **Automatic Updates**: The controller watches for changes and updates tunnel configuration automatically

## Accessing Services

Once configured, your service will be accessible at:

```
http://nginx.yourdomain.com
```

Or with HTTPS (if SSL/TLS is configured in Cloudflare):

```
https://nginx.yourdomain.com
```

### SSL/TLS Configuration

1. Go to Cloudflare Dashboard → SSL/TLS
2. Set encryption mode to "Full" or "Full (strict)"
3. Cloudflare will automatically provision SSL certificates for your domain

## Architecture: Hybrid Approach

This setup supports a hybrid approach with Tailscale:

- **Tailscale Operator**: For internal/admin services (Grafana, Prometheus, Kubernetes dashboard)
  - Private access via Tailscale tailnet
  - Only accessible to authenticated Tailscale users
  
- **Cloudflare Tunnel**: For public-facing web applications
  - Public internet access
  - Protected by Cloudflare's DDoS protection and WAF
  - Can add Cloudflare Access for additional authentication

Both can coexist in the same cluster without conflicts, allowing you to:
- Keep internal services private and secure
- Expose public services with Cloudflare's security features
- Use the best tool for each use case

## Security Recommendations

1. **Enable Cloudflare WAF**: Protect against common web attacks
2. **Configure SSL/TLS**: Set to "Full" or "Full (strict)" mode
3. **Set up Firewall Rules**: Create rules to block malicious traffic
4. **Consider Cloudflare Access**: Add authentication for sensitive public services
5. **Rate Limiting**: Configure rate limiting rules in Cloudflare
6. **DDoS Protection**: Automatically enabled by default

## Troubleshooting

### Controller Pod Not Running

1. Check pod status:
   ```bash
   kubectl get pods -n cloudflare-tunnel-ingress-controller
   ```

2. Check pod logs:
   ```bash
   kubectl logs -n cloudflare-tunnel-ingress-controller -l app.kubernetes.io/name=cloudflare-tunnel-ingress-controller
   ```

3. Verify API token and account ID are correct
4. Check that the tunnel exists in Cloudflare dashboard

### Service Not Accessible

1. Check Ingress status:
   ```bash
   kubectl get ingress nginx-cloudflare-ingress
   ```

2. Verify the service exists and has endpoints:
   ```bash
   kubectl get svc nginx-cloudflare
   kubectl get endpoints nginx-cloudflare
   ```

3. Check DNS records in Cloudflare dashboard:
   - Go to DNS → Records
   - Verify the record was created automatically

4. Verify tunnel status in Cloudflare dashboard:
   - Zero Trust → Networks → Tunnels
   - Ensure tunnel is active and connected

5. Check Cloudflare SSL/TLS settings:
   - Ensure encryption mode is set correctly
   - Check for any SSL errors

### DNS Record Not Created

1. Verify domain is managed by Cloudflare
2. Check API token has `Zone:DNS:Edit` permission
3. Check controller logs for errors
4. Manually create DNS record if needed (CNAME to tunnel)

### Tunnel Connection Issues

1. Check tunnel status in Cloudflare dashboard
2. Verify `cloudflared` connectors are running:
   ```bash
   kubectl get pods -n cloudflare-tunnel-ingress-controller | grep cloudflared
   ```

3. Check connector logs:
   ```bash
   kubectl logs -n cloudflare-tunnel-ingress-controller -l app=cloudflared
   ```

## References

- [Cloudflare Tunnel Ingress Controller GitHub](https://github.com/STRRL/cloudflare-tunnel-ingress-controller)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Kubernetes Ingress Documentation](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Find Cloudflare Account and Zone IDs](https://developers.cloudflare.com/fundamentals/get-started/basic-tasks/find-account-and-zone-ids/)

## Summary

The Cloudflare Tunnel Ingress Controller provides a modern, secure, and cost-effective way to expose Kubernetes services to the public internet. It integrates seamlessly with Kubernetes Ingress resources, automatically manages tunnels and DNS records, and provides enterprise-grade security features through Cloudflare's global network. Combined with the Tailscale Operator for internal services, this setup offers a comprehensive solution for both public and private service exposure.

