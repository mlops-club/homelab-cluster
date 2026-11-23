# Architecture Decision Records

**Purpose**: Index the architecture decision records (ADRs) for the homelab cluster

**Scope**: One folder per decision under `.ai/docs/adr/`, numbered in order

**Overview**: Each ADR folder holds the research that led to a decision (`research.md`), POC notes
    (`<tool>-poc.md`), the decision
    record itself (`decision.md`) once it is made, and any supporting images. Research is written first
    and reviewed in its own PR; proofs of concept follow; the decision record cites both
    and reviewed in its own PR; proofs of concept follow; the decision record cites both. A small
    decision can keep its alternatives inside `decision.md` and skip the separate research file

**Related**: `.ai/docs/CLUSTER_HA_AUDIT.md`

---

| ADR | Topic | Research | POC | Decision |
|---|---|---|---|---|
| [0001](0001-outside-in-monitoring/) | Outside-in monitoring, SLOs and alerting | [research.md](0001-outside-in-monitoring/research.md) | [grafana-poc.md](0001-outside-in-monitoring/grafana-poc.md) | [decision.md](0001-outside-in-monitoring/decision.md) (Accepted); follow-up [telemetry-plan.md](0001-outside-in-monitoring/telemetry-plan.md) |
| [0002](0002-traefik-default-certificate/) | Traefik default certificate instead of per-namespace secret copies | In decision (Alternatives considered) | None | [decision.md](0002-traefik-default-certificate/decision.md) (Accepted) |
