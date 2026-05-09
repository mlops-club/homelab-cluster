# Mandatory Rules

**Purpose**: Quality gates, coding standards, and mandatory rules for all AI agents

**Scope**: Rules that apply to all work done in this repository

**Overview**: Defines the mandatory rules and standards that every AI agent must follow.
    Peer document to ai-context.md; together with index.yaml they form the three core
    documents every agent reads first.

**Dependencies**: AGENTS.md (entry point), ai-context.md (project context), index.yaml (navigation)

**Exports**: Quality gates, coding standards, git rules, documentation rules

---

## Quality Gates

### File Header Standard

All files require headers with these mandatory fields:
- **Purpose** - Brief description
- **Scope** - What this covers
- **Overview** - Comprehensive explanation

Additional fields for code files:
- **Dependencies**, **Exports**, **Interfaces**, **Implementation**

For full details, see `.ai/docs/FILE_HEADER_STANDARDS.md`.

## Git Rules

### Branch Requirements

- **NEVER** work directly on main branch
- Create feature branches BEFORE making changes
- Branch naming: `feat/<name>`, `fix/<issue>`, `docs/<update>`

### Commit Standards

- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `chore:`, `build:`, `perf:`
- Include descriptive messages
- Update documentation with code changes

### Quality Checks Before PR

- **Before creating a PR**, run `prek pr` to validate all checks pass. Do not push until prek passes or the user explicitly approves pushing despite failures.
- This project uses [prek](https://github.com/phitoduck/prek) for git hooks and PR validation. Prek is configured in `prek.toml` and enforces:
  - Trailing whitespace and end-of-file fixes
  - YAML, JSON, TOML validation
  - Merge conflict detection
  - Private key detection
  - Gitleaks secret scanning
  - Large file detection (500KB max)
  - Conventional commit format

## Documentation Rules

### Atemporal Language

Avoid temporal language in documentation:
- No timestamps, no "currently", no "now"
- No "recently added", no "will be added"
- State facts, not history

### Architecture Diagrams

Architecture diagrams use **Mermaid** in markdown files. Keep diagrams alongside the documentation they illustrate.

### File Placement

| File Type | Location |
|-----------|----------|
| How-to guides | `.ai/howto/` |
| Conceptual docs | `.ai/docs/` |
| Templates | `.ai/templates/` |
| Ansible playbooks | `k3s-ansible/` |
| Private network components | `network/private/` |
| Public network components | `network/public/` |
| Storage configuration | `storage/` |
| Application deployments | `apps/` |

## Security Rules

- Never commit secrets or credentials
- Use `.env` files (gitignored) for sensitive values
- All secrets in Kubernetes must be created via `bootstrap.sh` or documented in BOOTSTRAP.md
- Validate that gitleaks passes before pushing
