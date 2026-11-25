# OpenTelemetry Operator

The [OpenTelemetry Operator](https://github.com/open-telemetry/opentelemetry-operator) manages
the lifecycle of OpenTelemetry Collectors via the `OpenTelemetryCollector` custom resource.
A Collector is a pluggable pipeline (receivers → processors → exporters) for logs, metrics,
and traces; the Operator turns one CR into the right Deployment / DaemonSet / sidecar plus
its ConfigMap, Service, and RBAC.

## What this directory deploys

| File             | What it does |
|------------------|--------------|
| `values.yaml`    | Helm values for the `opentelemetry-operator` chart. Pins the default Collector image to the `contrib` distribution (only one shipping `k8sattributes` + `prometheus`). Webhook TLS via cert-manager. |
| `collector.yaml` | One `OpenTelemetryCollector` CR (Deployment mode) plus its ServiceAccount/ClusterRole/Binding. Scrapes NVIDIA DCGM exporter, enriches with k8s.* resource attributes, exports metrics to the `eric-sandbox` Better Stack source over OTLP HTTP. |
| `vitals-collector.yaml` | The `vitals` `OpenTelemetryCollector` CR (DaemonSet mode) plus its ServiceAccount/ClusterRole/Binding. Sends five metrics to Grafana Cloud: CPU and memory per node and per pod (kubelet_stats) and CPU package temperature per node (node-exporter hwmon). Allow-list filter, three labels, 60 s interval. |
| `PROPOSAL.md` | Why the vitals Collector looks the way it does: every telemetry stream that reaches Grafana Cloud, its series or GB, the levers that raise each one, the free-tier budget, and the rollback. |

## Pipeline

```
nvidia-dcgm-exporter  ──prometheus scrape──▶  k8sattributes  ──▶  batch  ──▶  otlphttp ──▶  Better Stack (eric-sandbox)
(gpu-operator ns,                              (stamps k8s.pod.*,                            https://s2518436.us-east-9
 cluster-node-4)                               k8s.namespace.name,                            .betterstackdata.com)
                                               k8s.node.name, …)
```

## Why a Deployment, not a DaemonSet

The Collector is currently a single-replica Deployment because the only target it scrapes
(dcgm-exporter) is a single pod cluster-wide. A DaemonSet Collector becomes useful when we add
the `filelog` receiver to tail pod logs from each node's `/var/log/pods` — that's the obvious
follow-up. Splitting metrics (Deployment) from logs (DaemonSet) is the standard OTel pattern
for clusters of this size.

## Helm release

Managed by `helmfile.yaml.gotmpl` as the `opentelemetry-operator` release in the
`opentelemetry-operator-system` namespace. The chart is pinned to `0.115.0` from the
`open-telemetry` Helm repo (`https://open-telemetry.github.io/opentelemetry-helm-charts`).

```bash
source .env && helmfile -f helmfile.yaml.gotmpl -l name=opentelemetry-operator diff
source .env && helmfile -f helmfile.yaml.gotmpl -l name=opentelemetry-operator apply
```

The release's presync hook creates the `betterstack-sandbox-ingest-token` Secret in the
`opentelemetry` namespace from `BETTERSTACK_SANDBOX_INGEST_TOKEN` in `.env`. The postsync hook
applies `collector.yaml` (Operator CRDs must exist first).

## Dependencies

| Depends on      | Why |
|-----------------|-----|
| `cert-manager`  | Operator's admission webhook uses cert-manager-issued TLS (`admissionWebhooks.certManager.enabled=true`). |
| `gpu-operator`  | Provides the `nvidia-dcgm-exporter` Service and pods the Collector scrapes. |
| `.env` token    | `BETTERSTACK_SANDBOX_INGEST_TOKEN` for the OTLP exporter. |

## Better Stack source

Data lands in the `eric-sandbox` source (Source ID `2518436`) in the **Sandbox** team —
isolated from the production "Your team". See the conversation that introduced this for the
isolation validation done in the Better Stack UI.

## Verification

After `helmfile apply` completes:

```bash
# Operator + Collector pods
kubectl get pods -n opentelemetry-operator-system
kubectl get pods -n opentelemetry

# Collector logs — should show successful scrapes and OTLP exports, no 401s
kubectl logs -n opentelemetry -l app.kubernetes.io/name=gateway-collector --tail=50
```

In Better Stack, open `eric-sandbox` → Live tail or Dashboards. DCGM metric names start with
`DCGM_FI_DEV_*` (e.g. `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_MEM_COPY_UTIL`,
`DCGM_FI_DEV_FB_USED`). Each datapoint should carry `k8s.pod.name=nvidia-dcgm-exporter-…`,
`k8s.namespace.name=gpu-operator`, `k8s.node.name=cluster-node-4`.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Collector CR created but no pod | Operator pod's webhook not ready — check `kubectl get pods -n opentelemetry-operator-system` and `kubectl describe opentelemetrycollector gateway -n opentelemetry`. |
| Collector logs show `connection refused` to dcgm | dcgm-exporter pod not running on `cluster-node-4` — `kubectl get pods -n gpu-operator -l app=nvidia-dcgm-exporter -o wide`. |
| OTLP exporter logs `401 Unauthorized` | `betterstack-sandbox-ingest-token` Secret is missing or wrong — check the Secret in the `opentelemetry` namespace and re-run the presync hook by re-applying the release. |
| Metrics arrive in Better Stack but lack `k8s.*` attributes | k8sattributes processor RBAC missing — `kubectl auth can-i list pods --as=system:serviceaccount:opentelemetry:otel-collector`. |
