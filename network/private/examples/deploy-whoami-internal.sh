#!/bin/bash -euox pipefail

# Create the whoami-internal namespace
kubectl create namespace whoami-internal --dry-run=client -o yaml | kubectl apply -f -

# Note: The Ingress names no TLS secret; traefik-private serves its default certificate
# (priv-wildcard-tls, TLSStore in network/private/traefik/values.yaml).
# No manual secret copying is needed.

# Deploy whoami service
kubectl apply -f network/private/examples/whoami-internal.yaml
