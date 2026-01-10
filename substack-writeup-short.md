# Phase 1: Setting up VPN and installing K3s

## Step 1: get a bunch of nodes!

I have 3 nodes in my homelab:

- cluster-node-1
- cluster-node-2
- cluster-node-3

I installed Ubuntu 24.04 LTS on each of them, and made an admin user called `main` and of course I configured the hostname to be `cluster-node-{i}`.

## Step 2: Set up Tailscale VPN free tier to make connecting to my nodes easy

You need network access to a kubernetes cluster for 2 reasons:

1. access to the individual nodes when you're installing the various kubernetes binaries (control plane and data plane) on your nodes
2. access to the control plane load balancer API via `kubectl` thereafter

I set up each node manually by connecting each one to a monitor, keyboard, and mouse. So, at this point, I had never actually connected to one over a network.

I did not want to have to track down the IP addresses assigned to my nodes by my router, so instead, I skipped to setting up a tailscale VPN. Tailscale has an amazing free tier and several friends and blogs I found recommended it.

The steps are easy:

1. Go to tailscale.com and sign up for a free account
2. Go to "Add a device"
3. Run this command they give you on a linux machine

```bash
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key=xxx
```

I did this on each machine. It launches a persistent, durable daemon process managed by `systemd` which maintains a persistent connection to the tailscale network. In other words, even if you reboot the machine, it will automatically join itself back to the VPN!

### Step 3: making passwordlessSSH easy

Passwordless SSH is very convenient.

Thanks to the previous step, I could connect to all my nodes via SSH like this:

```bash
ssh main@cluster-node-1
```

But it would still prompt me for a password.

**Note:** `cluster-node-1` is the hostname of the machine. And because of that, tailscale created a DNS name for it called `cluster-node-1` that resolves whenever you are connected to the tailnet! Amazing! No need to track down the nodes' individual private IP addresses!

To make `ssh main@cluster-node-1` stop prompting me for a password, I generated a new SSH key and added it to the `authorized_keys` file for the `main` user on each machine.

```bash
# generate a new ssh key (you can also re-use an existing one)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

# a slick 1-liner to register your key in authorized_keys on each node
for node in {1..3}; do
    ssh-copy-id -i ~/.ssh/id_ed25519.pub "main@cluster-node-$node"
done
```

## Step 4: Install kubernetes! (specifically `k3s`)

Kubernetes is a set of a few different serivces and daemons that all work together to coordinate the starting and stopping of containers across a set of machines. Google "kubernetes architecture" to learn more about the individual components.

Depending on whether a node is a "master" (control plane node) or a "worker" (data plane node), the services that need to run on it vary.

There are a bunch of "distros" of kubernetes, which are basically different sets of these dependencies--and in some cases--different implementations of them.

I went with `k3s` because it is popular and lightweight and easy to install. There are other distros that fit this description, though, so it was by no means the only choice.

Typically, to install `k3s` on a set of 3 nodes, you'd run commands like this:

```bash
# on node 1 (a master node)
curl -sfL https://get.k3s.io | sh - --server https://cluster-node-1:6443
# would print some <token> which later nodes can use to join the same cluster

# on node 2 (a worker node)
curl -sfL https://get.k3s.io | sh - --server https://cluster-node-1:6443 --token <token>

# on node 3 (a worker node)
curl -sfL https://get.k3s.io | sh - --server https://cluster-node-1:6443 --token <token>
```

Pretty easy!

... But there are also several configuration options you may need/want to consider. So, I opted to do the install with Ansible instead. See the next section.

## Step 4.5: But actually, Ansible has some advantages

Ansible is an infrastructure-as-code tool for installing and configuring software across a set of machines... like we have.

The theoretical benefits of IaC are:

1. It's declarative: do not worry about the existing state on your machines
2. It comes with a `reset` (teardown) functionality which makes it easy to wipe a cluster clean without having to re-install the whole OS and format harddrives
3. It's code, so, it encourages version control

Number [2] was the most important to me. Since I only have 3 nodes, I won't have a separate cluster for "prod" and another for "non-prod" (staging, dev, or whatever else). So, I wanted to be able to easily reset my cluster and start from scratch as I experiment with different settings.

[This YouTube video](https://www.youtube.com/watch?v=CbkEWcUZ7zM) by TechnoTim walks through [a forked GitHub repo of `k3s-ansible`](https://github.com/timothystewart6/k3s-ansible) that I used to install `k3s` on my nodes.

I cloned the repo:

```bash
git clone https://github.com/timothystewart6/k3s-ansible.git
```

Then I edited the `inventory/cluster/hosts.ini` file to point to my nodes:

```ini
[master]
cluster-node-1 ansible_user=main
cluster-node-2 ansible_user=main
cluster-node-3 ansible_user=main

[node]

[k3s_cluster:children]
master
node
```

This declares that all 3 of my nodes will be `master` nodes (part of the control plane). Both the master and worker nodes have the `agent` installed and run on them, but in addition, master nodes also run the `server` service.

In order for a kubernetes cluster to be "highly available" (does not go down if a single node fails), you need at least 3 master nodes.

I also changed one other file: `inventory/cluster/group_vars/all.yml` 

There are many defaults already set in the cloned repo. I only changed these:

1. `system_timezone: America/Denver`
2. `flannel_iface: enp1s0` Because the NUCs use that interface instead of `eth0`.
3. `metal_lb_ip_range: 192.168.50.200-192.168.50.220` Because the NUCs (my nodes) are on a LAN with IPs in `192.168.50.(up to 199)` and the IPs assigned to pods by metallb must not overlap with those.

If you do not know what values to use for [2] and [3], ask Claude Code, Cursor agent, etc. to run commands against one of your nodes to find out.

At a high level,

1. Flannel plays the role of a Container Network Interface (CNI) which is responsible for assigning IP addresses to containers and ensuring they can communicate with each other. There are multiple options for the CNI made available by `k3s-ansible`: Calico, Cilium, and Flannel. I am no expert, so I went with the default (Flannel). 

2. MetalLB is a load balancer for the control plane API. It is used to balance traffic between the master nodes. Whenever you run `kubectl` commands from your local machine (laptop), `kubectl` makes calls to MetalLB which then forwards the request to any of the master nodes running the control plane API server. The ansible script made sure MetalLB was running on every node--as opposed to only running it on one node, which would be a single point of failure and therefore not highly available.

To deploy the ansible script, there is a pip-installable CLI tool called `ansible-galaxy` which can install the collections needed by the script.

AI can help you from there.

## Step 5: Fetch the kubeconfig file so `kubectl` will work

To control the kubernetes cluster from your laptop, you will need to use `kubectl` to issue commands to it.

First install `kubectl` on your laptop:

```bash
brew install kubectl
```

Then fetch the kubeconfig file from the cluster node:

```bash
# may fail due to /etc/rancher/k3s/k3s.yaml not being readable by the main user
# if this happens, fiddle with file permissions or do a manual copy/paste or
# use chmod on the file... basically, do whatever you need to copy it to this location locally
scp main@cluster-node-1:/etc/rancher/k3s/k3s.yaml ~/.kube/config
```

The one thing you will need to change about the file is the server URL. It will be something like this:

```yaml
clusters:
- cluster:
    insecure-skip-tls-verify: true
    server: https://127.0.0.1:6443
```

Obviously, `127.0.0.1` (localhost) is not the right IP for you to reach out to from your laptop. Instead, change it to

```yaml
clusters:
- cluster:
    insecure-skip-tls-verify: true
    server: https://cluster-node-1:6443
```

And you are set! Note that the end of the `~/.kube/config` file will look like this:

```yaml
users:
- name: default
  user:
    client-certificate-data: LS0tLS1CRUdJTiBDRVJUSU...
    client-key-data: LS0tLS1CRUdJTi...
```

The `client-certificate-data` and `client-key-data` are the base64 encoded versions of a certificate that was generated by `k3s` when you launched the server process on the node.

If you ever use Ansible to teardown and re-deploy k3s onto your cluster, then this certificate will no longer be regenerated and you will get SSL errors any time you use `kubectl`. To fix it, you will need to fetch this certificate from one of the cluster nodes again and update your local `~/.kube/config` file.

## Hooray! 🎉 🎉 🎉 You have a working kubernetes cluster on a network you can access from your anywhere!
