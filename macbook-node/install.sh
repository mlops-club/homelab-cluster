#!/usr/bin/env bash
# Purpose: Create the cluster-node-5 Lima VM on the MacBook and join it to the k3s cluster as cluster-node-5
# Scope: User-level steps only (Lima VM lifecycle, join token copy, readiness wait); root steps live in host-setup.sh
# Overview: Idempotent. Creates and starts the VM from lima-k3s-agent.yaml if it does not exist, streams the cluster
#     joins the tailnet as NODE_NAME (tag:homelab, Tailscale SSH) through an interactive login URL, streams the cluster
#     join token from a server node straight into the guest over SSH (never written to the Mac's disk), enables the
#     k3s-agent systemd unit, and waits for the Node to report Ready. Run `sudo ./host-setup.sh apply` first so the
#     bridged network (socket_vmnet + Lima sudoers) exists, and again afterwards to register the boot LaunchDaemon.
# Dependencies: limactl, kubectl (context pointing at the homelab cluster), SSH access to a server node with sudo
# Interfaces: ./install.sh   (env: INSTANCE, NODE_NAME, TOKEN_HOST override defaults)
# Implementation: Token read with `sudo cat /var/lib/rancher/k3s/server/node-token` on TOKEN_HOST

set -euo pipefail
cd "$(dirname "$0")"

INSTANCE="${INSTANCE:-cluster-node-5}"
NODE_NAME="${NODE_NAME:-cluster-node-5}"
TOKEN_HOST="${TOKEN_HOST:-main@cluster-node-1}"

if ! limactl list -q | grep -qx "${INSTANCE}"; then
  limactl create --name "${INSTANCE}" --tty=false ./lima-k3s-agent.yaml
fi
if [[ "$(limactl list "${INSTANCE}" --format '{{.Status}}')" != "Running" ]]; then
  if launchctl print "system/io.lima-vm.daemon.${INSTANCE}" >/dev/null 2>&1; then
    echo "LaunchDaemon owns this instance; waiting for it to start the VM"
    until [[ "$(limactl list "${INSTANCE}" --format '{{.Status}}')" == "Running" ]]; do sleep 5; done
  else
    limactl start "${INSTANCE}" --tty=false
  fi
fi

# Join the tailnet first: Tailscale SSH and the NAS route (nas-nfs uses the NAS's Tailscale IP) depend on it.
# `tailscale up` prints a login URL and blocks until an admin approves it in the browser.
if ! limactl shell "${INSTANCE}" -- tailscale status >/dev/null 2>&1; then
  limactl shell "${INSTANCE}" -- sudo tailscale up --ssh --hostname="${NODE_NAME}" --advertise-tags=tag:homelab
fi

if ! limactl shell "${INSTANCE}" -- sudo test -s /etc/rancher/k3s/cluster-token; then
  ssh -o BatchMode=yes "${TOKEN_HOST}" 'sudo cat /var/lib/rancher/k3s/server/node-token' |
    limactl shell "${INSTANCE}" -- sudo sh -c 'umask 077; cat >/etc/rancher/k3s/cluster-token'
fi
limactl shell "${INSTANCE}" -- sudo systemctl enable --now k3s-agent

echo "waiting for node ${NODE_NAME} to be Ready"
kubectl wait --for=condition=Ready "node/${NODE_NAME}" --timeout=300s
kubectl get node "${NODE_NAME}" -o wide
