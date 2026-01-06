# Free SSL Solution: Using `*.mlops-club.org`

## Current Approach

We use `*.mlops-club.org` (single-level wildcard) which is **fully covered by Cloudflare's free Universal SSL**.

## Why This Works

Cloudflare's free Universal SSL automatically covers:
- ✅ Root domain: `mlops-club.org`
- ✅ Single-level wildcards: `*.mlops-club.org` (e.g., `whoami.mlops-club.org`, `app.mlops-club.org`)

It does **NOT** cover:
- ❌ Multi-level wildcards: `*.lab.mlops-club.org` (requires paid Total TLS)

## Architecture

1. **Cloudflare Tunnel**: Routes all `*.mlops-club.org` subdomains (without explicit DNS records) to Traefik
2. **Traefik**: Routes traffic based on host headers (e.g., `whoami.mlops-club.org` → whoami service)
3. **TLS**:
   - **Edge**: Cloudflare automatically provisions SSL certificates for `*.mlops-club.org` (free Universal SSL)
   - **Origin**: Traefik terminates TLS using cert-manager + Let's Encrypt certificate (`mlops-wildcard-tls`)

## No Manual DNS Records Needed

Unlike the previous approach with `*.lab.mlops-club.org`, we don't need to create explicit DNS records for each subdomain. Cloudflare Tunnel automatically routes all `*.mlops-club.org` subdomains to Traefik, and Cloudflare's Universal SSL covers them automatically.

## Verification

Test any subdomain:
```bash
curl -v https://whoami.mlops-club.org
```

The SSL certificate should be automatically provisioned by Cloudflare within 5-15 minutes.
