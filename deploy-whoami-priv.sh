#!/bin/bash -euox pipefail

# Create the whoami-priv namespace
kubectl create namespace whoami-priv --dry-run=client -o yaml | kubectl apply -f -

# Deploy whoami service
kubectl apply -f whoami-deployment/tailscale-traefik-internal.yaml

