# How-To: Create a PR

**Purpose**: Guide AI agents through creating a structured pull request, monitoring CI checks, fixing failures, and resolving AI review comment threads

**Scope**: All pull requests in the homelab-cluster repository, usable by any AI coding assistant

**Overview**: Walks through the full PR lifecycle from branch to review-clean: verify the branch
    and sync with main, gather context, generate a structured PR body from a template, push and
    create the PR on GitHub, then actively monitor CI checks and review comments — fixing failures
    and resolving addressed comment threads until the PR is clean.

**Dependencies**: `git` CLI, `gh` CLI (authenticated), `.ai/templates/pr-body.md.template`, `prek`

**Exports**: A GitHub pull request with structured description, passing checks, and resolved review threads

**Related**: `.ai/templates/pr-body.md.template`, `.github/PULL_REQUEST_TEMPLATE.md`

**Difficulty**: intermediate

---

## Prerequisites

- **git CLI**: Available on PATH
- **gh CLI**: Authenticated with `gh auth status`
- **prek**: Installed (`uv add --dev prek && uv run prek install`)
- **Branch**: Working branch is not `main` — changes are committed and ready for review

## Steps

### Step 1 — Verify Branch and Sync with Main

Before anything else, confirm you are not on `main` and pull the latest changes.

```bash
# Confirm current branch is not main
git rev-parse --abbrev-ref HEAD
```

If the current branch is `main`, **stop** and inform the user. Do not create PRs from `main`.

```bash
# Pull latest main and rebase onto it
git fetch origin main
git rebase origin/main
```

If there are merge conflicts:
1. Report the conflicting files to the user
2. Resolve conflicts with minimal changes, preserving the intent of both sides
3. `git add <resolved-files>` then `git rebase --continue`
4. If conflicts are ambiguous, ask the user how to resolve

### Step 2 — Run Quality Checks

```bash
prek pr
```

If prek fails:
1. Fix the issues
2. Re-run `prek pr`
3. If failures persist after 2 attempts, report to the user

### Step 3 — Gather Context

Collect the information needed to generate the PR title and body.

```bash
# Current branch name
git rev-parse --abbrev-ref HEAD

# Commits being submitted (compared to main)
git log main..HEAD --oneline

# Changed files summary
git diff main...HEAD --stat

# Repo owner and name (for API calls later)
gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
```

Derive the PR title from the branch name and commit messages:
- Use conventional commit format: `feat:`, `fix:`, `docs:`, etc.
- Keep under 70 characters
- If the user provided a title via arguments, use that instead

### Step 4 — Generate PR Body

1. Read the PR body template at `.ai/templates/pr-body.md.template`
2. Fill in all four sections based on the diff, commit messages, and understanding of the changes:
   - **Executive Summary** — What changed, what was wrong before, how this addresses it. Write for a reviewer with no prior context.
   - **List of Changes** — One bullet per logical change, grouped by file/module/concern. Use "Add", "Update", "Remove", "Fix" as leading verbs.
   - **Risk Assessment** — Pick one level from the template's pick-list. Explain blast radius briefly.
   - **New Behavior** — Observable effect after merging. Use "No runtime behavior change." for docs-only PRs.
3. Do not include the template's HTML header in the output — only the filled-in sections.

### Step 5 — Push and Create PR

```bash
# Push branch to remote (set upstream tracking)
git push -u origin <branch-name>

# Create the PR targeting main
gh pr create --title "<title>" --body "<filled-body>"
```

Report the PR URL to the user.

Save the PR number for subsequent steps:
```bash
gh pr view --json number --jq '.number'
```

### Step 6 — Monitor Checks and Comments (Loop)

Poll CI checks and review comments until the PR is clean.

**6a. Poll checks:**

```bash
gh pr checks <number>
```

- If all checks pass -> proceed to 6b
- If any check is pending -> wait 15 seconds, re-poll
- If any check fails -> go to Step 7
- After 10 minutes without resolution -> ask the user whether to continue waiting or abort

**6b. Query review comments:**

After checks pass, wait 30 seconds for AI review workflows to post comments, then query:

```bash
# Inline review comments
gh api repos/{owner}/{repo}/pulls/{number}/comments \
  --jq '.[] | {id: .id, path: .path, line: .line, body: .body, author: .user.login}'

# Review-level comments
gh api repos/{owner}/{repo}/pulls/{number}/reviews \
  --jq '.[] | select(.state != "APPROVED") | {id: .id, author: .user.login, state: .state, body: .body}'
```

- If no actionable comments -> report success, go to Step 8
- If actionable comments exist -> go to Step 7

### Step 7 — Fix Issues

**7a. Diagnose the problem:**

For CI failures:
```bash
# Find the failed run
gh run list --branch <branch> --limit 5 --json databaseId,status,conclusion \
  --jq '.[] | select(.conclusion == "failure")'

# View failed logs
gh run view <run-id> --log-failed
```

For review comments:
- Read the referenced file and line
- Understand the reviewer's concern
- Prioritize CI failures over style comments
- If review comments conflict with each other, report to the user rather than choosing

**7b. Fix the code:**

- Make minimal, targeted changes to address the issue
- Do not refactor surrounding code

**7c. Resolve addressed comment threads via GraphQL:**

The REST API cannot resolve review threads — use GraphQL.

Query unresolved threads:
```bash
gh api graphql -f query='
  query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $number) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
            comments(first: 1) {
              nodes {
                body
                path
                line
              }
            }
          }
        }
      }
    }
  }
' -f owner="<owner>" -f repo="<repo>" -F number=<number>
```

Resolve each thread whose issue has been fixed:
```bash
gh api graphql -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
      thread {
        isResolved
      }
    }
  }
' -f threadId="<thread-id>"
```

**Only resolve threads whose referenced code issues have actually been fixed.** Never resolve a comment thread without fixing the code first.

**7d. Commit and push:**

```bash
git add <changed-files>
git commit -m "<type>: <description of fix>"
git push
```

Use conventional commit format for all fix commits.

**7e. Return to Step 6.**

**Hard cap: 3 fix cycles.** After 3 iterations, report remaining issues to the user and stop.

### Step 8 — Completion

Report to the user:
- PR URL
- Number of fix iterations (0 if none needed)
- Summary of fixes applied (if any)

**Do NOT auto-merge.**

---

## Behavioral Rules

- Never resolve a comment thread without fixing the referenced code first
- Use conventional commits for all fix commits
- Never commit secrets or `.env` files
- Derive owner/repo from `gh repo view --json owner,name` — do not hardcode
- Prioritize CI failures over style comments
- If review comments conflict, report to user rather than choosing
- Never force-push
- Do not modify files unrelated to the PR's changes when fixing review comments

## Success Criteria

- [ ] PR created with all four body sections filled in
- [ ] PR targets `main` branch
- [ ] CI checks pass (or failures reported to user after 3 fix cycles)
- [ ] Addressed review comment threads are resolved via GraphQL
- [ ] PR URL reported to user
