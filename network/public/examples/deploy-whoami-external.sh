#!/bin/bash -euox pipefail

# Create the whoami-external namespace
kubectl create namespace whoami-external --dry-run=client -o yaml | kubectl apply -f -

# Deploy whoami service
kubectl apply -f network/public/examples/whoami-external.yaml

