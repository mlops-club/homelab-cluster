#!/bin/bash -euox pipefail

source .env

# Install cert-manager CRDs (using latest stable version)
CERT_MANAGER_VERSION="v1.13.3"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.crds.yaml"

# Add cert-manager Helm repository
helm repo add jetstack https://charts.jetstack.io
helm repo update

# Install cert-manager
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=false \
  --wait

# Create Cloudflare API token secret for cert-manager
kubectl create secret generic cloudflare-api-token \
  --from-literal=api-token="${CLOUDFLARE_API_TOKEN}" \
  --namespace cert-manager \
  --dry-run=client -o yaml | kubectl apply -f -

# Create ClusterIssuer for Let's Encrypt with Cloudflare DNS challenge
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-cloudflare
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${ACME_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-cloudflare
    solvers:
    - dns01:
        cloudflare:
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
      selector:
        dnsZones:
        - ${CLOUDFLARE_DOMAIN}
EOF

echo "cert-manager installed and configured!"
echo "Waiting for ClusterIssuer to be ready..."
kubectl wait --for=condition=Ready clusterissuer/letsencrypt-cloudflare --timeout=60s || echo "ClusterIssuer may take a moment to become ready"

