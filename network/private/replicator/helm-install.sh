#!/bin/bash -euox pipefail

# Install Reflector operator to continuously replicate TLS certificates to all namespaces
# This ensures certificates stay up-to-date across all namespaces when cert-manager renews them

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

source "${PROJECT_ROOT}/.env"

echo "Installing Reflector operator..."

# Add emberstack Reflector Helm repository
helm repo add emberstack https://emberstack.github.io/helm-charts
helm repo update emberstack

# Install Reflector operator
helm upgrade --install reflector emberstack/reflector \
  --namespace reflector \
  --create-namespace \
  --wait

echo "Reflector operator installed successfully!"

# Wait for the priv-wildcard-tls secret to exist (created by cert-manager)
echo "Waiting for priv-wildcard-tls secret to be created by cert-manager..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
  if kubectl get secret priv-wildcard-tls -n traefik-private &>/dev/null; then
    echo "Secret found! Adding replication annotations..."
    break
  fi
  echo "Waiting for secret... (${elapsed}s/${timeout}s)"
  sleep 2
  elapsed=$((elapsed + 2))
done

if kubectl get secret priv-wildcard-tls -n traefik-private &>/dev/null; then
  # Add annotations to enable replication to all namespaces
  # Reflector will automatically replicate this secret to all namespaces
  kubectl annotate secret priv-wildcard-tls -n traefik-private \
    reflector.v1.k8s.emberstack.com/reflection-allowed: "true" \
    reflector.v1.k8s.emberstack.com/reflection-auto-enabled: "true" \
    --overwrite || true
  
  echo "Secret replication annotations added. priv-wildcard-tls will be automatically replicated to all namespaces."
else
  echo "Warning: priv-wildcard-tls secret not found. It will be created by cert-manager."
  echo "Run this script again after the certificate is issued, or manually add the annotations:"
  echo "  kubectl annotate secret priv-wildcard-tls -n traefik-private \\"
  echo "    reflector.v1.k8s.emberstack.com/reflection-allowed=true \\"
  echo "    reflector.v1.k8s.emberstack.com/reflection-auto-enabled=true"
fi

