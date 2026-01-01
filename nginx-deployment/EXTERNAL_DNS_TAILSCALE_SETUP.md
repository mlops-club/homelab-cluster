# External-DNS + Tailscale Setup for Stable Domain Names

## Request Summary

The goal was to create a stable domain name (`nginx-internal.mlops-club.org`) that maps to a Tailscale LoadBalancer IP address. The requirements were:

1. **Stable Domain**: The domain should remain consistent even when Kubernetes services are deleted and recreated
2. **Tailscale Access**: Service should only be accessible to devices on the Tailscale network
3. **Public DNS Resolution**: The DNS record should be publicly resolvable (anyone can resolve the domain to an IP)
4. **Cloudflare DNS Management**: Use Cloudflare DNS (domain `mlops-club.org`) but **not** Cloudflare Tunnels
5. **Automatic Management**: DNS records should be automatically created/updated when services change

## Approach Taken

### 1. Solution Identified: External-DNS Operator

External-DNS is a Kubernetes operator that automatically synchronizes exposed Kubernetes services and ingresses with DNS providers. It supports Cloudflare and can watch for LoadBalancer services with Tailscale IPs.

### 2. Manifest Modification

Modified `nginx-deployment/manifest-internal-tailscale-cloudflare.yaml` to:

- Use unique Kubernetes resource names (`nginx-internal-tailscale`) to avoid conflicts with other manifests
- Add External-DNS annotation: `external-dns.alpha.kubernetes.io/hostname: nginx-internal.mlops-club.org`
- Keep Tailscale LoadBalancer configuration intact

**Key Changes:**
```yaml
metadata:
  name: nginx-internal-tailscale
  annotations:
    tailscale.com/expose: "true"
    external-dns.alpha.kubernetes.io/hostname: nginx-internal.mlops-club.org
spec:
  type: LoadBalancer
  loadBalancerClass: tailscale
```

### 3. External-DNS Installation & Configuration

#### Initial State
- External-DNS was already installed via Helm
- However, it was configured to use **AWS Route 53** provider instead of Cloudflare
- This caused errors: `failed to list hosted zones: operation error Route 53`

#### Configuration Steps

1. **Cloudflare API Token Secret** (already existed):
   ```bash
   kubectl create secret generic cloudflare-api-token \
     --from-literal=cloudflare_api_token=<token> \
     --namespace kube-system
   ```

2. **Helm Values Configuration**:
   - Cloudflare configuration was present in Helm values but not being used
   - The deployment was using `--provider=aws` instead of `--provider=cloudflare`

3. **Helm Upgrade Command** (corrected configuration):
   ```bash
   helm upgrade --install external-dns external-dns/external-dns \
     --namespace kube-system \
     --set "provider=cloudflare" \
     --set "env[0].name=CF_API_TOKEN" \
     --set "env[0].valueFrom.secretKeyRef.name=cloudflare-api-token" \
     --set "env[0].valueFrom.secretKeyRef.key=cloudflare_api_token" \
     --set "cloudflare.zoneIdFilter=d0bf3fa4e9e8504213ce8228e83c4c6f" \
     --set "domainFilters[0]=mlops-club.org" \
     --set "sources[0]=service" \
     --set "sources[1]=ingress" \
     --set "serviceTypeFilter[0]=LoadBalancer" \
     --set "txtOwnerId=k3s-cluster" \
     --wait --timeout 5m
   ```

   **Key Fix**: The External-DNS Helm chart's `cloudflare.apiTokenSecretName` configuration was not properly mapping the secret to the `CF_API_TOKEN` environment variable that the Cloudflare provider expects. The solution is to explicitly set the environment variable using the `env` section in Helm values.

### 4. Current Status

✅ **Fully Working**: External-DNS is now properly configured and operational:
- ✅ External-DNS is configured with `--provider=cloudflare`
- ✅ Cloudflare API token is properly passed via `CF_API_TOKEN` environment variable
- ✅ DNS records are automatically created/updated for services with External-DNS annotations
- ✅ `nginx-internal.mlops-club.org` resolves to the Tailscale LoadBalancer IP

## How It Works (When Fully Configured)

1. **Tailscale Operator** assigns a Tailscale IP (e.g., `100.113.199.17`) to the LoadBalancer service
2. **External-DNS** detects the service with the `external-dns.alpha.kubernetes.io/hostname` annotation
3. **External-DNS** creates/updates an A record in Cloudflare: `nginx-internal.mlops-club.org → 100.113.199.17`
4. **DNS Resolution**: Anyone can resolve `nginx-internal.mlops-club.org` to the Tailscale IP
5. **Access Control**: Only devices on the Tailscale network can actually reach the IP

## Files Modified

- `nginx-deployment/manifest-internal-tailscale-cloudflare.yaml`
  - Changed resource names to `nginx-internal-tailscale`
  - Added External-DNS annotation with domain `nginx-internal.mlops-club.org`

## Troubleshooting

### Issue: "invalid credentials: key & email must not be empty"

**Problem**: The External-DNS Helm chart's native Cloudflare secret mapping (`cloudflare.apiTokenSecretName`) was not working correctly. The Cloudflare provider expects the `CF_API_TOKEN` environment variable, but it wasn't being set.

**Solution**: Explicitly set the environment variable in the Helm configuration:
```bash
--set "env[0].name=CF_API_TOKEN" \
--set "env[0].valueFrom.secretKeyRef.name=cloudflare-api-token" \
--set "env[0].valueFrom.secretKeyRef.key=cloudflare_api_token"
```

### Verifying the Setup

1. **Check External-DNS Pod Status**:
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/name=external-dns
   # Should show: STATUS Running, READY 1/1
   ```

2. **Check External-DNS Logs**:
   ```bash
   kubectl logs -n kube-system -l app.kubernetes.io/name=external-dns
   # Should show successful DNS record creation, no credential errors
   ```

3. **Verify Service and DNS**:
   ```bash
   # Check service has Tailscale IP
   kubectl get svc nginx-internal-tailscale
   
   # Test DNS resolution
   dig +short nginx-internal.mlops-club.org
   # Should return the Tailscale IP (e.g., 100.113.199.17)
   ```

4. **Test Access**: From a Tailscale-connected device:
   ```
   http://nginx-internal.mlops-club.org
   ```

## Architecture Benefits

- **Stable Domain Names**: Domain persists even when services are recreated
- **Automatic Management**: No manual DNS record updates needed
- **Public DNS, Private Access**: DNS is publicly resolvable but service is only accessible via Tailscale
- **Kubernetes Native**: Uses standard Kubernetes annotations and LoadBalancer services
- **Works Alongside Other Solutions**: Can coexist with Cloudflare Tunnel for public services

## Related Documentation

- `TAILSCALE_OPERATOR_SETUP.md` - Tailscale operator configuration
- `CLOUDFLARE_TUNNEL_SETUP.md` - Cloudflare Tunnel setup (for public services)
- `nginx-deployment/manifest-internal-tailscale.yaml` - Tailscale-only version
- `nginx-deployment/manifest-public-cloudflare.yaml` - Public Cloudflare Tunnel version

## References

- [External-DNS Documentation](https://kubernetes-sigs.github.io/external-dns/)
- [External-DNS Cloudflare Provider](https://kubernetes-sigs.github.io/external-dns/latest/docs/tutorials/cloudflare/)
- [Tailscale Kubernetes Operator](https://tailscale.com/kb/1236/kubernetes-operator)

