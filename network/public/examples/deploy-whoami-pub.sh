#!/bin/bash -euox pipefail

# Create the whoami-public namespace
kubectl create namespace whoami-public --dry-run=client -o yaml | kubectl apply -f -

# Deploy whoami service
kubectl apply -f network/public/examples/whoami-public.yaml

