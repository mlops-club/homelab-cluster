#!/bin/bash -euox pipefail

# Create the whoami-internal namespace
kubectl create namespace whoami-internal --dry-run=client -o yaml | kubectl apply -f -

# Note: The priv-wildcard-tls secret is automatically replicated to all namespaces
# by reflector when the certificate is created/updated in traefik-private namespace.
# No manual secret copying is needed.

# Deploy whoami service
kubectl apply -f network/private/examples/whoami-internal.yaml

