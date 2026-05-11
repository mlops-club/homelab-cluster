# AI Agent Instructions for homelab-cluster

## STOP

**You MUST read the documents listed below BEFORE doing anything else.**

**Your output will be rejected if you skip this step.** No exceptions. No shortcuts. Do not summarize, guess, or proceed from memory.

### Required Reading (in order)

1. **READ** `.ai/ai-context.md` — Project context and patterns
2. **READ** `.ai/ai-rules.md` — Quality gates and mandatory rules
3. **READ** `.ai/index.yaml` — Navigation and resource index
4. **IDENTIFY** relevant howtos, docs, and templates for your task
5. **INFORM** the user which documents you read and which you will use for this task

### Verification

After reading, you **MUST** state:
- Which documents you read
- Which howtos, docs, or templates are relevant to your task
- Which you will use

**Only then may you proceed.**

---

## Project Overview

Bare-metal Kubernetes homelab running K3s on Intel NUCs, providing production services for the MLOps Club with dual-stack networking (private via Tailscale, public via Cloudflare Tunnel).

**Type**: infrastructure
**Status**: in-development

## Navigation

### Three Core Documents
- **`.ai/ai-context.md`** - Project context, architecture, patterns
- **`.ai/ai-rules.md`** - Quality gates, mandatory rules
- **`.ai/index.yaml`** - Complete repository map

### How-To Guides
See `.ai/howto/` for step-by-step guides on common tasks.

### Templates
See `.ai/templates/` for reusable file templates.

## Development Guidelines

### Git Workflow

- Create feature branches before making changes
- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `chore:`, `build:`, `perf:`
- Never work directly on main branch

### Before Creating a PR

- [ ] **Run prek**: Before creating a PR, run `prek pr` to validate all checks pass. Fix any failures before pushing.
- [ ] All changes tested against the cluster (where applicable)
- [ ] Documentation updated
- [ ] No secrets committed

## Common Operations

This project uses shell scripts for automation. Use these instead of running raw commands.

### Cluster Operations

| Command | Description |
|---------|-------------|
| `./bootstrap.sh` | Full cluster bootstrap (idempotent) |
| `DEPLOY_EXAMPLES=true ./bootstrap.sh` | Bootstrap with example apps |
| `cd k3s-ansible && ./run deploy` | Deploy K3s cluster via Ansible |
| `cd k3s-ansible && ./run reset` | Tear down K3s cluster |

### Network Operations

| Command | Description |
|---------|-------------|
| `./network/private/helm-install.sh` | Install/upgrade private network stack |
| `./network/public/helm-install.sh` | Install/upgrade public network stack |

### Kubernetes Debugging

| Command | Description |
|---------|-------------|
| `kubectl get pods -n <namespace>` | List pods in a namespace |
| `kubectl logs -f <pod> -n <namespace>` | Stream pod logs |
| `kubectl describe pod <pod> -n <namespace>` | Describe pod status |
| `kubectl get events -n <namespace> --sort-by='.lastTimestamp'` | Recent events |
| `kubectl get ingressroute -A` | List all Traefik IngressRoutes |

### Quality Checks

| Command | Description |
|---------|-------------|
| `prek pr` | Run all quality checks before PR |
| `prek run` | Run pre-commit hooks on staged files |

## Getting Help

1. Check `.ai/ai-context.md` for project context
2. Check `.ai/ai-rules.md` for rules and standards
3. Review `.ai/howto/` for guides
4. Check existing code for patterns

---

## Roadmap-Driven Development

### Feature vs Initiative

| Concept | Scope | Location |
|---------|-------|----------|
| **Feature** | Single deliverable, 1+ milestones | `.roadmap/features/` |
| **Initiative** | Strategic grouping of features | `.roadmap/initiatives/` |

### Lifecycle

```
planning/ -> active/ -> completed/
```

### Detection Patterns

**Plan a feature** - User says "plan feature X", "roadmap X", "break down X":
- Route to: `.ai/howto/how-to-plan-a-feature.md`

**Continue feature work** - User says "continue with X", "resume X", "next milestone":
- Route to: `.ai/howto/how-to-continue-feature-work.md`

**Update progress** - User says "update progress", "mark complete":
- Route to: `.ai/howto/how-to-update-progress.md`

**Create a PR** - User says "create PR", "open PR", "submit PR", "push for review":
- Route to: `.ai/howto/how-to-create-a-pr.md`

### Templates

Feature: `.ai/templates/feature-*.md.template`
