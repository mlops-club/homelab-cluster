# Architecture Decision Records

**Purpose**: Index the architecture decision records (ADRs) for the homelab cluster

**Scope**: One folder per decision under `.ai/docs/adr/`, numbered in order

**Overview**: Each ADR folder holds the research that led to a decision (`research.md`), POC notes
    (`<tool>-poc.md`), the decision
    record itself (`decision.md`) once it is made, and any supporting images. Research is written first
    and reviewed in its own PR; proofs of concept follow; the decision record cites both. A small
    decision can keep its alternatives inside `decision.md` and skip the separate research file

**Related**: `.ai/docs/CLUSTER_HA_AUDIT.md`

---

| ADR | Topic | Research | POC | Decision |
|---|---|---|---|---|
| [0002](0002-traefik-default-certificate/) | Traefik default certificate instead of per-namespace secret copies | In decision (Alternatives considered) | None | [decision.md](0002-traefik-default-certificate/decision.md) (Accepted) |
| [0006](0006-macbook-cluster-node/) | MacBook Pro as k3s agent node `cluster-node-5` (Lima VM, Tailscale, always-on host) | In decision (Alternatives considered) | In decision (Verification) | [decision.md](0006-macbook-cluster-node/decision.md) (Accepted) |
