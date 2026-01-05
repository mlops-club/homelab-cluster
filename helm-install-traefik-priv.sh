#!/bin/bash -euox pipefail

source .env

# Create the traefik-private namespace
kubectl create namespace traefik-private --dry-run=client -o yaml | kubectl apply -f -

# Add Traefik Helm repository
helm repo add traefik https://helm.traefik.io/traefik
helm repo update

# Create temporary values file for Traefik configuration
TEMP_VALUES=$(mktemp)
cat > "$TEMP_VALUES" << 'EOF'
ingressClass:
  enabled: true
  name: traefik-private
  isDefaultClass: false

service:
  type: LoadBalancer
  loadBalancerClass: tailscale
  annotations:
    tailscale.com/expose: "true"
    external-dns.alpha.kubernetes.io/hostname: "traefik.priv.mlops-club.org"

# Disable automatic HTTP to HTTPS redirect
entryPoints:
  web:
    address: ":8000/tcp"
    http:
      redirections:
        entryPoint:
          to: web
          scheme: ""
EOF

# Install Traefik in traefik-private namespace
# Configure it to be exposed via Tailscale LoadBalancer with External-DNS registration
helm upgrade --install traefik-private traefik/traefik \
  --namespace traefik-private \
  --values "$TEMP_VALUES" \
  --wait

# Clean up temporary values file
rm -f "$TEMP_VALUES"

