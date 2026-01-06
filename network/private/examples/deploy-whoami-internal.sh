#!/bin/bash -euox pipefail

# Create the whoami-internal namespace
kubectl create namespace whoami-internal --dry-run=client -o yaml | kubectl apply -f -

# Copy wildcard TLS secret into whoami-internal (required for Ingress TLS reference)
kubectl delete secret priv-wildcard-tls -n whoami-internal --ignore-not-found
kubectl get secret priv-wildcard-tls -n traefik-private -o yaml \
  | sed 's/namespace: traefik-private/namespace: whoami-internal/' \
  | kubectl apply -n whoami-internal -f -

# Deploy whoami service
kubectl apply -f network/private/examples/whoami-internal.yaml

