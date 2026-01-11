#!/bin/bash -euox pipefail

# Deploy whoami service
kubectl apply -f network/public/examples/whoami-public.yaml

