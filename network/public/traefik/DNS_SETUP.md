# DNS Setup for Cloudflare Tunnel

## Issue

The Cloudflare Tunnel ingress controller may not automatically create a wildcard DNS record for `*.mlops-club.org`. DNS resolution is required before Cloudflare Tunnel can route traffic.

## Solution: Create Wildcard DNS Record

You need to manually create a wildcard DNS record in Cloudflare:

### Steps

1. **Go to Cloudflare Dashboard**
   - Navigate to your domain: `mlops-club.org`
   - Go to **DNS** → **Records**

2. **Add Wildcard CNAME Record**
   - Click **Add record**
   - **Type**: CNAME
   - **Name**: `*` (wildcard)
   - **Target**: `3366d3d0-3cc8-45f9-8472-1e37dff5b795.cfargotunnel.com` (your tunnel hostname)
   - **Proxy status**: Proxied (orange cloud) ✅
   - Click **Save**

3. **Verify Tunnel Hostname**
   ```bash
   kubectl get ingress -n traefik-public traefik-public-catchall -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
   ```
   Use this hostname as the target for the CNAME record.

### Why This Is Needed

- **DNS Resolution**: DNS must resolve `whoami.mlops-club.org` to Cloudflare's IPs before any routing can happen
- **Cloudflare Tunnel Routing**: Once DNS resolves, Cloudflare Tunnel routes based on host headers to Traefik
- **Wildcard Record**: A single wildcard record `*.mlops-club.org` covers all subdomains

### Verification

After creating the DNS record, wait 1-2 minutes for DNS propagation, then test:

```bash
# Check DNS resolution
dig +short whoami.mlops-club.org

# Should return Cloudflare IPs (e.g., 104.21.x.x or 172.67.x.x)

# Test HTTPS
curl -v https://whoami.mlops-club.org
```

### Alternative: Check Controller Logs

If the controller should be creating DNS records automatically, check its logs:

```bash
kubectl logs -n cloudflare-tunnel-ingress-controller -l app=cloudflare-tunnel-ingress-controller
```

Look for messages about DNS record creation.

