#!/usr/bin/env bash
# Purpose: Remove cluster-node-5 from the k3s cluster and delete its Lima VM
# Scope: Cluster Node object and the cluster-node-5 Lima instance; root host settings are reverted by host-setup.sh
# Overview: Drains the node (DaemonSets ignored, emptyDir data discarded), deletes the Node object so the cluster
#     stops tracking it, then stops and deletes the VM and its disk. Run `sudo ./host-setup.sh revert` first if
#     the boot LaunchDaemon is installed, otherwise launchd restarts the VM while it is being deleted.
# Dependencies: limactl, kubectl
# Interfaces: ./uninstall.sh   (env: INSTANCE, NODE_NAME override defaults)
# Implementation: Every step tolerates an already-removed resource so the script is safe to re-run

set -euo pipefail

INSTANCE="${INSTANCE:-cluster-node-5}"
NODE_NAME="${NODE_NAME:-cluster-node-5}"

if launchctl print "system/io.lima-vm.daemon.${INSTANCE}" >/dev/null 2>&1; then
  echo "LaunchDaemon io.lima-vm.daemon.${INSTANCE} is loaded; run 'sudo ./host-setup.sh revert' first" >&2
  exit 1
fi
if kubectl get node "${NODE_NAME}" >/dev/null 2>&1; then
  kubectl drain "${NODE_NAME}" --ignore-daemonsets --delete-emptydir-data --timeout=120s || true
  kubectl delete node "${NODE_NAME}"
fi
if limactl list -q | grep -qx "${INSTANCE}"; then
  limactl stop "${INSTANCE}" 2>/dev/null || limactl stop -f "${INSTANCE}" || true
  limactl delete "${INSTANCE}"
fi
echo "removed ${NODE_NAME} and Lima instance ${INSTANCE}"
