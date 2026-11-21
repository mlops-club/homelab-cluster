# Studio OpenTelemetry POC: plan

**Purpose**: Plan for full-stack OpenTelemetry on the CTDL Golden Rules Studio, run as an isolated copy on the
homelab cluster and viewed in Grafana Cloud. Written after the research, before deploying; changes made while
building are marked *(as built)*.

**Related**: [Write-up](../../.ai/docs/adr/0001-outside-in-monitoring/studio-otel-poc.md) ·
[Teardown](../../.ai/docs/adr/0001-outside-in-monitoring/studio-otel-teardown.md) ·
`monitoring/terraform-studio-otel/`

---

## 1. Goal and constraints

| Goal | Constraint |
|---|---|
| One connected trace per interaction, from the browser to the server | Production (`golden-rules-studio`) must not be touched |
| Web vitals per page; backend latency and errors per page's API calls | ctdl-xtra is public: only app instrumentation goes there |
| User, catalog, rule and build on every span | Few, wide spans (Honeycomb); no separate metrics; no cluster metrics |
| A Grafana dashboard per page, in Terraform | Everything reversible, with a teardown |

## 2. What the research settled

Full notes with sources: the research file kept with the POC evidence (`evidence/studio-otel/research.md`).

| Topic | Finding | Consequence |
|---|---|---|
| Honeycomb Web SDK 1.5.1 | Exports OTLP/HTTP to any endpoint without an API key (`skipOptionsValidation`). Web vitals are **spans** (`FCP`, `LCP`, `INP`, `CLS`, `TTFB`) with `<vital>.value`, `.rating`… Adds browser, page and `session.id` attributes. Metrics and logs exporters are on by default | Use it for vitals, errors, session; turn metrics/logs off; send to the Studio's own origin |
| Its peers | `auto-instrumentations-web` (pinned to 0.65) and `context-zone` are **optional** | Don't install them: no Zone.js, no auto fetch/click spans. The app makes its few spans itself |
| Honeycomb guidance (agent-skills `otel-instrumentation`, "span or attribute") | Prefer attributes on existing spans; new spans only for interesting, aggregable work; roll-ups as `stats.*`, timings as `*.duration_ms`; set up in code; no-op without an endpoint | One server span per request + middleware attributes; `ce.stats.*` roll-ups; sub-spans only for cold loads, publishing, jobs |
| Semantic conventions 1.45.0 | `user.id`, `user.roles`, `session.id` (development) replace deprecated `enduser.*`; `vcs.*`, `cicd.*` release candidate; no "triggered by" attribute; `gen_ai.*` moved to its own repo | Use `user.*`, `session.id`; custom `ce.cicd.triggered_by`; `gen_ai.*` only on the agent-run request |
| Python | FastAPI instrumentation 0.66b2, `exclude_spans=["receive","send"]`; `OTEL_SDK_DISABLED` | Optional extra `otel`; code setup, inert without `OTEL_EXPORTER_OTLP_*ENDPOINT` |
| Grafana Cloud free tier | 50 GB traces/month, 14-day retention; TraceQL metrics capped at a 24 h range | Dashboard defaults to 24 h; volume estimate in the write-up |
| Collector 0.165.0 | `k8s_attributes` with `filter.namespace` needs only a namespaced Role; browser spans must not be matched to a pod | Separate receivers and pipelines for browser and backend |

## 3. Design

```text
browser ──(same origin) /otlp/v1/traces──► Ingress ──► collector :4319  ─┐ traces/browser: truncate attrs
   │ traceparent + baggage (user.id, session.id, ce.page)               │
   ▼                                                                    ├─► Grafana Cloud OTLP gateway ─► Tempo
Studio (FastAPI) ──── OTLP http :4318 ──────────────► collector :4318  ─┘ traces/backend: k8s_attributes,
                                                                          k8s.cluster.name, drop fast polls/assets
```

- **Browser** (lazy chunk, only when the server configures it; *(as built)* the config is inlined in `index.html`
  and telemetry starts before the first render, after a first version that fetched it missed a hard load's first
  requests): `page_view` span per route
  (ready time, API counts), one client span per API call carrying `traceparent` + `baggage`, plus the SDK's
  vitals and error spans.
- **Server**: one wide server span per request (who, what, size, storage roll-ups, error detail); sub-spans
  `snapshot.load`, `golden.publish`, `golden.publish_page`; background `score.run` and `catalog.add` traces linked
  to the request that started them.
- **Infra context**, never in ctdl-xtra: `vcs.*`/`cicd.*` baked into the image by `otel/build-otel.sh` (from
  `GITHUB_*` in Actions); `deployment.*`/`service.namespace` set by `otel/deploy-otel.sh`; `k8s.*` and
  `k8s.cluster.name` by the collector.

## 4. Isolation (no production impact)

| Write path in the Studio | Production | Isolated instance |
|---|---|---|
| Annotations log, rulesets, manifest, profiles, scores, pending scores | Azure `xtra-cli-output/zz-scratch-review-ui-v3` | Local root `/data/root` on its own PVC |
| Golden dataset publishing (approve, verdicts, reset) | Azure `xtra-golden-sets` | `/data/golden` (`GOLDEN_DATASETS_GOLDEN_ROOT`) |
| Extract outputs copied for scoring | read from `xtra-cli-output` | `GOLDEN_DATASETS_XTRA_SOURCE=/data/xtra-source` (empty) |
| Add a catalog (crawls) | `xtra-cli-output` | `GOLDEN_DATASETS_CRAWLS_ROOT=/data/root` |
| AI runs (K2) | K2 in-cluster | Off: no K2 key, and a local root turns them off in code |
| Credentials | `azure-sas` (racwdl), `k2-api` | **None**: no Azure or K2 Secret exists in the namespace |

The PVC is seeded once from a laptop: `golden-datasets sync` (prod → local folder) for two small catalogs and a
copy of their published golden datasets, both run under a guard that makes every Azure write method raise.

*(as built)* A read-only SAS was the first plan; the Azure CLI login had expired, so the seed used production's
SAS **locally, in one process, with writes disabled in code**, and the instance got no Azure credentials at all.

## 5. Steps

1. Backend telemetry module, middleware, sub-spans; tests (ctdl-xtra) ✔
2. Web telemetry: facade + lazy chunk; tests ✔
3. Local end-to-end with a collector in Podman: connected traces, session ids, noise ✔
4. Deploy repo `otel/`: Dockerfile, build/deploy/setup/seed/teardown scripts, collector config, manifest, workflow ✔
5. Grafana Cloud OTLP token *(as built: via the stack's auth-app proxy, see write-up)* ✔
6. Deploy, seed, run `bench/otel_tour.py` (two users, three rounds, both catalogs), screenshots ✔ *(as built: twice,
   on builds `6308326` and `3b9e67b`; images pushed from inside the cluster)*
7. Terraform dashboard (`monitoring/terraform-studio-otel/`), one section per page ✔
8. Write-up, attribute table, volume estimate, teardown ✔

## 6. Decisions under ambiguity

See the write-up's "Decisions" section; it is the maintained list.
