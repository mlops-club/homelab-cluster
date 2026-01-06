#!/bin/bash -euox pipefail

# Create the whoami-priv namespace
kubectl create namespace whoami-priv --dry-run=client -o yaml | kubectl apply -f -

# Copy wildcard TLS secret into whoami-priv (required for Ingress TLS reference)
kubectl delete secret priv-wildcard-tls -n whoami-priv --ignore-not-found
kubectl get secret priv-wildcard-tls -n traefik-private -o yaml \
  | sed 's/namespace: traefik-private/namespace: whoami-priv/' \
  | kubectl apply -n whoami-priv -f -

# Deploy whoami service
kubectl apply -f network/private/examples/whoami-internal.yaml

