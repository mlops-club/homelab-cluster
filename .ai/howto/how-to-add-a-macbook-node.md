# How-To: Add a MacBook as a Cluster Node

**Purpose**: Step-by-step setup that turns an Apple Silicon MacBook into an always-on k3s worker node

**Scope**: A fresh Apple Silicon MacBook Pro (macOS 26.4+) joining the homelab cluster as `cluster-node-N`; also covers verification, day-2 operations and removal

**Overview**: The Mac runs a Lima VM (Virtualization.framework, Ubuntu arm64) that is bridged onto the
    LAN, joins the tailnet with `tag:homelab` and Tailscale SSH, and runs the k3s agent. macOS is set to
    stay awake with the lid closed, start the VM at boot, and restart it after any crash. The design and
    its trade-offs are in ADR 0006; this guide is the procedure. `cluster-node-5` (M2 Max, 12 cores,
    32 GB) is used as the example throughout.

**Dependencies**: `macbook-node/` (`lima-k3s-agent.yaml`, `host-setup.sh`, `install.sh`, `uninstall.sh`), Homebrew, `kubectl` with the cluster context, Tailscale admin access, SSH to `cluster-node-1`

**Exports**: A Ready node `cluster-node-N` reachable as `ssh main@cluster-node-N`

**Related**: `.ai/docs/adr/0006-macbook-cluster-node/decision.md`, `.ai/docs/NODE_REGISTRY.md`, `BOOTSTRAP.md`, `.ai/ai-rules.md` (Container Image Rules)

**Difficulty**: intermediate

---

## Prerequisites

- Apple Silicon MacBook on macOS 26.4 or later, on AC power, on the home LAN (Wi-Fi or a USB-C
  Ethernet adapter)
- At least 60 GB free on the Mac's disk (the VM disk is sparse and can grow to 256 GiB; keep more free
  space than it can still grow into)
- An admin account on the Mac (several steps prompt for its password)
- From the Mac: `kubectl` pointing at the cluster, and `ssh main@cluster-node-1` working (Tailscale SSH)
- A Tailscale admin who can approve a device (the tailnet policy lets `autogroup:admin` apply
  `tag:homelab`; no policy change is needed)

## Steps

### Step 1: Choose the node name and MAC

Pick the next free `cluster-node-N`: check `.ai/docs/NODE_REGISTRY.md`, `kubectl get nodes`, and the
Tailscale machines list. Pick a guest MAC that no other node uses; the convention is
`52:55:55:50:00:0N` (`cluster-node-5` → `52:55:55:50:00:05`).

```bash
export NODE_NAME=cluster-node-5 MAC_ADDRESS=52:55:55:50:00:05
```

### Step 2: Prepare macOS (System Settings, by hand)

1. **Turn FileVault off**, so the VM starts after an unattended reboot. See ADR 0006, decision 8
   ([FileVault off](../docs/adr/0006-macbook-cluster-node/decision.md#filevault-off)).
2. **Set Charge Limit to 80%**. Where the setting is, why 80%, and a screenshot are in ADR 0006,
   decision 7 ([Battery](../docs/adr/0006-macbook-cluster-node/decision.md#battery-charge-limit)).
3. Make sure the Wi-Fi network is saved (it reconnects at boot before anyone logs in).

### Step 3: Install Lima and socket_vmnet

```bash
brew install lima socket_vmnet
```

### Step 4: Apply host settings (first pass)

From the repo root:

```bash
sudo macbook-node/host-setup.sh apply
```

This saves the current `pmset` settings to a backup, then sets: no sleep (including lid closed),
no standby/Power Nap, wake on LAN; installs `socket_vmnet` to `/opt/socket_vmnet` and Lima's sudoers
file so the bridged network can start. The VM does not exist yet, so the LaunchDaemon is skipped.

To bridge over an Ethernet adapter instead of Wi-Fi, change `interface: en0` under `networks.bridged`
in Lima's `networks.yaml` (in Lima's `_config` directory) to the adapter's `enX` before Step 5.

### Step 5: Create the VM and join the cluster

```bash
NODE_NAME=$NODE_NAME MAC_ADDRESS=$MAC_ADDRESS macbook-node/install.sh
```

`install.sh` sizes the VM from the host (all cores; RAM minus 8 GiB; override with `CPUS=` and
`MEMORY_GIB=`), boots it, and installs k3s, Tailscale and the `main` user. It then runs
`tailscale up` inside the VM, which prints a login URL and waits:

1. Open the URL, sign in as a tailnet admin, and click **Connect** (screenshots in ADR 0006,
   "Joining the tailnet").
2. The script continues: it streams the cluster join token from `cluster-node-1` into the VM, starts
   `k3s-agent`, and waits for the node to be Ready.

### Step 6: Hand the VM to launchd (second pass)

```bash
sudo INSTANCE=$NODE_NAME macbook-node/host-setup.sh apply
```

This stops the VM that `install.sh` started and registers the LaunchDaemon
`io.lima-vm.daemon.$NODE_NAME`, which starts the VM at boot (before any login) and restarts it whenever
it exits.

### Step 7: Record the node

Add a row to `.ai/docs/NODE_REGISTRY.md` and open a PR.

## Verification

```bash
kubectl get node $NODE_NAME -o wide          # Ready, arm64, LAN IP
ssh main@$NODE_NAME 'hostname; sudo -n true && echo sudo-ok; tailscale status --self --peers=false'
sudo INSTANCE=$NODE_NAME macbook-node/host-setup.sh status   # pmset, socket_vmnet, sudoers, daemon running
fdesetup status                              # FileVault is Off
```

Optional crash test: `kill -9 $(cat "$(limactl list $NODE_NAME --format '{{.Dir}}')/ha.pid")`; the node is Ready again in about
30 seconds.

## Operations

| Task | Command |
|---|---|
| Stop the node before travelling (unplugged Macs then sleep normally) | `sudo INSTANCE=$NODE_NAME macbook-node/host-setup.sh pause` |
| Start it again | `sudo INSTANCE=$NODE_NAME macbook-node/host-setup.sh apply` |
| Resize CPU, memory or disk | `pause`, then `limactl edit $NODE_NAME --cpus N --memory G --disk G` (disk can only grow), then `apply` |
| Rebuild from scratch | `revert` and `uninstall.sh`, delete the device in the Tailscale console, then Steps 4–6 |

## Removal

```bash
sudo INSTANCE=$NODE_NAME macbook-node/host-setup.sh revert   # removes daemon, sudoers, socket_vmnet; restores pmset
NODE_NAME=$NODE_NAME macbook-node/uninstall.sh                # drains and deletes the node, deletes the VM
brew uninstall lima socket_vmnet
```

Then delete the device in the Tailscale admin console and remove the node's row from the registry.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `limactl stop` has no lasting effect | The LaunchDaemon restarts the VM (`KeepAlive=true`) | Use `host-setup.sh pause` |
| Pod on this node stuck in `ImagePullBackOff` with "no match for platform" | The image has no arm64 variant | Rebuild it multi-arch, or pin the workload with `nodeSelector: {kubernetes.io/arch: amd64}` (Container Image Rules in `.ai/ai-rules.md`) |
| `nas-nfs` volume mount times out | The VM is not on the tailnet (the NAS is mounted at its Tailscale IP) | `ssh` into the VM via `limactl shell $NODE_NAME` and check `tailscale status` |
| VM disk errors / filesystem read-only | The Mac's disk is full | Free space on the Mac, then restart the VM |
| "Superset/Terminal would like to access data from other apps" prompts | Running `docker` on the host against Docker Desktop | Not needed for this setup; grant the terminal app Full Disk Access if Docker is used |
