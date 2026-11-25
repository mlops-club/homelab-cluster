# Moved: the Studio OTel dashboards now live in the deploy repo

**As of 2026-11-25 this folder is history only. Don't `terraform apply` it.**

The three dashboards this root managed (*Studio OTel POC: pages*, *compare a selection*, *one trace*, folder
`studio-otel-poc`) were merged into one dashboard, **Golden Rules Studio** (uid `golden-rules-studio`), managed by
Terraform in the private repo `mlops-club/golden-rules-studio-deploy`, folder `grafana/`, with uptime checks and its
state in the cluster (Secret `golden-rules-studio-terraform/tfstate-default-grafana`).

The old dashboards and folder were destroyed from here (`terraform destroy`, 2026-11-25), after the new dashboard was
checked. The local state is now empty, so an apply here would recreate them as duplicates.

The files are kept as they were at `4bfd7b2`: `dashboard.tf` (pages, service map), `bubbleup.py` / `bubbleup.json`
(bubble-up), `otlp-token.sh` (the POC collector's OTLP token, unrelated to the move). The page screenshots the new
dashboard shows are still served from this repo, pinned to commit `278d4ad`.
