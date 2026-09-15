# Benchmarks

In-cluster benchmark suites for the homelab's model serving stack.

| Suite | Scope |
|---|---|
| [`guidellm/`](./guidellm/) | LLM inference latency + throughput against Ollama, via [GuideLLM](https://github.com/vllm-project/guidellm) |

Each suite is self-contained: a Kubernetes Job spec, a driver script, and a summarizer that produces a Markdown report in [`reports/`](./reports/).
