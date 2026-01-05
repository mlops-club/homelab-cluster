#!/bin/bash -euox pipefail

source .env

# Create the traefik-private namespace
kubectl create namespace traefik-private --dry-run=client -o yaml | kubectl apply -f -

# Issue wildcard TLS cert for *.priv.mlops-club.org via cert-manager (requires ClusterIssuer letsencrypt-cloudflare)
kubectl apply -f network/traefik-private/priv-wildcard-certificate.yaml

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
  ports:
    web:
      port: 80
      targetPort: 8000
    websecure:
      port: 443
      targetPort: 8443

ports:
  web:
    port: 80
    expose:
      default: true
    exposedPort: 80
    protocol: TCP
  websecure:
    port: 443
    expose:
      default: true
    exposedPort: 443
    protocol: TCP
    tls:
      enabled: true

# Configure TLS and HTTP to HTTPS redirect
entryPoints:
  web:
    address: ":8000/tcp"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":8443/tcp"
    http:
      tls:
        enabled: true

tls:
  stores:
    default:
      defaultCertificate:
        secretName: priv-wildcard-tls

# Additional arguments for redirect
additionalArguments:
  - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
  - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
  - "--entrypoints.web.http.redirections.entrypoint.permanent=true"
EOF

# Install Traefik in traefik-private namespace
# Configure it to be exposed via Tailscale LoadBalancer with External-DNS registration
helm upgrade --install traefik-private traefik/traefik \
  --namespace traefik-private \
  --values "$TEMP_VALUES" \
  --wait

# Clean up temporary values file
rm -f "$TEMP_VALUES"

