# Note: Total TLS Not Required

## Current Setup

We use `*.mlops-club.org` (single-level wildcard) which is **fully covered by Cloudflare's free Universal SSL**. Total TLS is **not needed**.

## When Would You Need Total TLS?

Total TLS would only be needed if you wanted to use multi-level wildcards like:
- `*.lab.mlops-club.org`
- `*.dev.mlops-club.org`

Since we use `*.mlops-club.org` instead, Cloudflare's free Universal SSL covers all our subdomains automatically.

## Current Architecture

- **Domain pattern**: `*.mlops-club.org` (single-level wildcard)
- **SSL coverage**: Free Universal SSL (automatic)
- **Cost**: $0/month
- **Total TLS required**: No

## If You Need Multi-Level Subdomains

If you ever need multi-level subdomains (e.g., `*.lab.mlops-club.org`), you would need to:
1. Enable Total TLS in Cloudflare Dashboard (SSL/TLS → Edge Certificates → Total TLS)
2. Cost: $10/month
3. Or use explicit DNS records for each subdomain (free, but manual)

But with our current `*.mlops-club.org` approach, this is not necessary.
