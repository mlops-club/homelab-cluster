# GPU Operator

The [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html) provisions everything Kubernetes needs to schedule GPU workloads: the container toolkit, the device plugin, DCGM metrics, MIG/MPS, and Node Feature Discovery (NFD).

## Cluster state assumed

- **GPU node**: `cluster-node-4` — a worker with one NVIDIA GeForce RTX 5080 (16 GB).
- **Host driver**: pre-installed on the node (driver 595.71.05, CUDA 13.2).
- **Distribution**: K3s on Ubuntu 24.04 — containerd lives at non-standard paths.

The operator is opinionated: by default it tries to install and own the NVIDIA driver. That collides with a host-installed driver, so this deployment turns `driver.enabled` off. See `values.yaml` for the full rationale.

## Helm release

Managed by `helmfile.yaml.gotmpl` as the `gpu-operator` release in the `gpu-operator` namespace. The chart is pinned at `v26.3.2` from the `nvidia` Helm repo (`https://helm.ngc.nvidia.com/nvidia`).

```bash
source .env && helmfile -f helmfile.yaml.gotmpl -l name=gpu-operator diff
source .env && helmfile -f helmfile.yaml.gotmpl -l name=gpu-operator apply
```

## How nodes are targeted

The chart bundles NFD. NFD labels every node with the hardware it discovers; only `cluster-node-4` ends up with `feature.node.kubernetes.io/pci-10de.present=true` (NVIDIA PCI vendor ID), and the operator's DaemonSets self-target on that label. No manual nodeSelector or taint is required.

Non-GPU pods keep using the default `runc` runtime even on the GPU node (`CONTAINERD_SET_AS_DEFAULT=false`). To run a pod on the GPU, opt in:

```yaml
spec:
  runtimeClassName: nvidia
  containers:
    - name: cuda
      image: nvcr.io/nvidia/cuda:13.0.1-base-ubuntu24.04
      resources:
        limits:
          nvidia.com/gpu: 1
```

## Verification

After the release reports `STATUS: deployed`, check that the operator's components landed on the GPU node:

```bash
kubectl get pods -n gpu-operator -o wide
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpus: .status.allocatable["nvidia.com/gpu"]}'
```

`cluster-node-4` should report `"gpus": "1"`. A quick end-to-end smoke test:

```bash
kubectl run cuda-smoke --rm -it --restart=Never \
  --image=nvcr.io/nvidia/cuda:13.0.1-base-ubuntu24.04 \
  --overrides='{"spec":{"runtimeClassName":"nvidia","containers":[{"name":"cuda-smoke","image":"nvcr.io/nvidia/cuda:13.0.1-base-ubuntu24.04","command":["nvidia-smi"],"resources":{"limits":{"nvidia.com/gpu":"1"}}}]}}' \
  -- nvidia-smi
```

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Toolkit pod healthy but pods see no GPU | Wrong `CONTAINERD_CONFIG` path — confirm K3s writes to `/var/lib/rancher/k3s/agent/etc/containerd/config.toml` from the `.tmpl` |
| `cuda-validator` Init crashloop | Host driver / CUDA mismatch with the operator's CUDA base image — check `nvidia-smi` on the node |
| Validator says no GPU detected | NFD has not labeled the node yet — `kubectl logs -n gpu-operator -l app.kubernetes.io/name=node-feature-discovery` |
| Operator targets the wrong nodes | Another node was labeled by mistake — `kubectl describe node` and look for `nvidia.com/gpu.present` |
