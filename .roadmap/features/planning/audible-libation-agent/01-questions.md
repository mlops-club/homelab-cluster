# Audible / Libation Agent: Questions (QRSPI: Q)

**Purpose**: Questions to answer before researching and designing an agent on K2 that browses Audible libraries via Libation and moves selected books to the homelab

**Scope**: Assumptions, facts to verify, and open ambiguities. No design decisions.

**Overview**: The goal is a conversation with Claude Code running inside K2 on the homelab: "what's new
    on my Audible accounts?", then "download these and put them in Audiobookshelf." This file lists
    what has to be true for that to work, what has been observed, and what only the user can decide.
    Questions tagged **[USER]** need the user's input. Questions tagged **[RESEARCH]** can be answered
    by reading code, docs, or the cluster.

---

## Observed facts (starting point)

These were checked against the live system and local machine, not inferred.

| Fact | Source |
|------|--------|
| K2 runs as StatefulSet `k2/k2-0`, pinned to `cluster-node-2`, image `cr.priv.mlops-club.org/k2/k2-agents:0.46.5-cc2.1.308-uv0.13.6` | `kubectl get sts k2 -n k2` |
| K2 pod has Claude Code and `uv` on PATH; no `dotnet`, no Libation | `kubectl exec k2-0 -- which ...` |
| K2 pod mounts only a 50Gi `local-path` PVC at `/var/lib/k2`. It has no NFS mount and cannot see the NAS audiobook library | StatefulSet spec |
| K2 runs as UID 10000, drops all capabilities, `automountServiceAccountToken: false` (no Kubernetes API access) | StatefulSet spec |
| K2 manifests are not in this repo (no `apps/k2/`, no reference on any branch) | `git log --all` |
| Audiobookshelf reads `/volume1/k8s-homelab/media/audiobooks/Books/` via a 500Gi RWX static PV (`audiobookshelf-audiobooks`) | `kubectl get pvc -n audiobookshelf` |
| The NAS holds 940 book folders | `ssh eric@nas ls ... \| wc -l` |
| Libation 14.2.2 is installed on the Mac with 2 Audible accounts, both `us` locale: Account A (954 library entries) and Account B (443) | `AccountsSettings.json`, `LibationContext.db` |
| Each Libation account stores `IdentityTokens` (Audible auth tokens) and a `DecryptKey` in `AccountsSettings.json` | `AccountsSettings.json` key names only |
| Libation marks only 9 books as downloaded (`BookStatus=1`); 1,388 are not | `LibationContext.db` |
| `~/Music/Libation/Books` is empty (books were moved to the NAS after download) | `ls` |
| Existing transfer procedure is manual `tar \| ssh eric@nas` from the Mac | `.ai/howto/how-to-add-audiobooks-to-audiobookshelf.md` |
| A prior agent-on-cluster pattern exists: `loseit-agent` namespace/deployment | `kubectl get deploy -n loseit-agent` |

The 9-vs-940 mismatch matters: **Libation's "downloaded" flag does not tell you what's on the homelab.**

---

## 1. Goal and interaction

1. **[USER]** Where do you want to have the conversation? K2 web UI / phone companion app, a terminal on the Mac attached to K2, or somewhere else (Slack, Open WebUI)?
2. **[USER]** On-demand only ("what's new?") or also proactive (a weekly digest: "5 new books since last check, want any?")?
3. **[USER]** What does "new" mean?
   - (a) added to an Audible account since the last check
   - (b) in an Audible library but not on the NAS
   - (c) both, reported separately
4. **[USER]** Should the agent ever download without asking (e.g. auto-download anything new on Account A), or always confirm first?
5. **[USER]** Is the scope only "list + download + move", or also: return/cancel, wishlist, ratings, pre-orders, podcasts, buying with credits? (Buying would be a much bigger permission.)
6. **[USER]** After the move, should the agent also trigger an Audiobookshelf library scan and confirm the book appears?

## 2. Audible accounts and credentials

7. **[USER]** Does the owner of Account B know about and agree to their Audible account being driven by an always-on agent on the homelab? Should those books be in the same Audiobookshelf library or a separate one?
8. **[USER]** Are there more Audible accounts or locales (e.g. `uk`, `de`) to add later?
9. **[USER]** Do you want to keep the Mac as the place where Audible login happens (log in on the Mac, then export tokens to the cluster), or log in once on the homelab and drop the Mac from the loop entirely?
10. **[RESEARCH]** How long do Libation/Audible `IdentityTokens` last? Does Libation refresh access tokens automatically using the refresh token, and what makes a refresh token expire (password change, deregistering the device, inactivity)?
11. **[RESEARCH]** Does each Libation login register a new "device" on the Audible account? Is there a device limit, and does running a second Libation instance (Mac + homelab) with the same tokens cause conflicts or deregistration?
12. **[RESEARCH]** Can `AccountsSettings.json` be copied as-is to another machine/container, or are tokens bound to the machine?
13. **[RESEARCH]** Does logging in require an interactive browser step (CAPTCHA, 2FA/OTP, approval email)? If yes, how would first login (or re-login) work headless on the cluster?
14. **[USER]** Where should Audible credentials live on the cluster: a Kubernetes Secret (as with other apps here), or something else? Is it acceptable that anyone/any agent with access to K2 could reach them?

## 3. Libation's headless and programmatic surface

15. **[RESEARCH]** Which Libation interfaces exist and run on Linux without a GUI?
    - `LibationCli` (commands like `scan`, `liberate`, `export`, `search`?)
    - The official Docker image (`rmcrackan/libation`) and its behavior (scan-and-liberate on a loop?)
    - Exact flags, exit codes, machine-readable output (JSON/CSV export)
16. **[RESEARCH]** Can `LibationCli` download a *specific* book by ASIN, or only "liberate everything not yet downloaded"? (This decides whether "download these 3 books" is possible without downloading 1,388.)
17. **[RESEARCH]** Can Libation be told "these books already exist elsewhere" (mark as downloaded / import existing files) so it doesn't redownload the 940 already on the NAS?
18. **[RESEARCH]** Where does Libation write its state (`LibationContext.db`, settings) and is that DB safe to read while Libation runs (SQLite WAL/locking)?
19. **[RESEARCH]** What does Libation output by default (`.m4b` single file vs. chapters, folder template `Title [ASIN]`)? Does the headless setup match the folder structure Audiobookshelf already uses?
20. **[RESEARCH]** Alternatives to Libation for the "list library" part: the `audible` Python package / `audible-cli` (mkb79) can list a library with the same kind of tokens and run under `uv`, which is already in the K2 image. Is it worth using for listing while Libation does download/decrypt? Or is one tool cleaner?
21. **[USER]** Is Libation itself a requirement, or is it just the tool you've been using? Would you accept a different tool if it's simpler headless?

## 4. Where things run on the homelab

22. **[USER]** Which shape do you picture?
    - (a) Install Libation into the K2 image and let Claude Code call it directly
    - (b) Run Libation as its own service (separate pod/namespace) and give the K2 agent a narrow way to talk to it (CLI over `kubectl exec`, a small HTTP API, or an MCP server)
    - (c) No preference, decide during design
23. **[RESEARCH]** How does K2 expose tools/skills to Claude Code inside it (project `AGENTS.md`, skills, MCP servers)? Can a K2 agent reach another in-cluster service over HTTP? K2 has no Kubernetes API token, so `kubectl exec` from K2 would need a new ServiceAccount + RBAC.
24. **[RESEARCH]** How was K2 deployed (manifests, image build, Harbor project)? Should those manifests be brought into this repo under `apps/k2/` as part of this work?
25. **[RESEARCH]** How does `loseit-agent` give an agent access to an external account? Is that a pattern to reuse?
26. **[RESEARCH]** Does decryption (AAX/AAXC to M4B) need much CPU/RAM? K2 is limited to 4Gi memory and pinned to `cluster-node-2`.

## 5. Storage and file movement

27. **[RESEARCH]** Can a pod write straight to the NAS audiobook PV (`audiobookshelf-audiobooks`, RWX NFS) instead of going through `tar | ssh`? What UID/permissions do existing files have, and will Audiobookshelf (step 5 of the howto: `chmod -R 777`) be able to read new files written by another UID?
28. **[USER]** Download straight into the Audiobookshelf folder, or into a staging folder first and then move? (Staging avoids Audiobookshelf scanning half-written files.)
29. **[USER]** Is the Mac still part of the flow at all after this, or does everything happen on the homelab?
30. **[RESEARCH]** How to match "on the NAS" with "in an Audible library"? By ASIN in the folder name (`Title [ASIN]`)? Do all 940 NAS folders have an ASIN? Do Audible-sourced and non-Audible books (e.g. O'Reilly, other imports) share that folder?
31. **[RESEARCH]** Disk space: free space on the NAS volume vs. size of the remaining ~1,388 library items, if everything were downloaded.

## 6. Safety, permissions, and failure modes

32. **[USER]** What actions should the agent never take without asking (delete files on NAS, overwrite an existing book, remove an account)?
33. **[USER]** When tokens expire or Audible asks for re-login, how do you want to be told (agent says so in chat, push notification, nothing)?
34. **[RESEARCH]** Does Audible's terms of service or rate limiting create any risk from automated library scans (how often is safe)?
35. **[USER]** Is K2 reachable only over Tailscale (private), and should it stay that way given it will hold Audible credentials?

## 7. Definition of done

36. **[USER]** Which of these must the first version do?
    - List new books per account
    - Download chosen books
    - Put them on the NAS where Audiobookshelf sees them
    - Trigger and verify an Audiobookshelf scan
    - Scheduled digest
    - Work with no Mac involved

---

## User answers

| # | Topic | Answer |
|---|-------|--------|
| 1 | Interface | Log into the K2 desktop client and run Claude Code there. That session needs access to everything required. No scheduled digest. |
| 2–3 | "New" | New since the last conversation. Review books that landed in that window and pick which to download. Many books not on the NAS are intentionally skipped. |
| 4 | Autonomy | Always confirm before downloading. User-driven chat, not a background agent. |
| 5 | Scope | List and download only. No returns, wishlist, or purchases. |
| 7 | Account B | Owner consents. Those books go into the same Audiobookshelf library (as today). |
| 9 | Logins | Open question: user wants options and trade-offs. Highest-uncertainty, most important area. |
| 21 | Libation | Not required. Hard needs: download books, and refresh/manage login tokens (today the desktop app does the browser auth flow). A Libation CLI is welcome if it works. |
| 22 | Shape | No preference. Top concern: login tokens must survive pod crashes/resets. Unclear what the K2 pod mounts and what a reset loses. |
| 28 | Destination | Download directly into the Audiobookshelf folder, provided there is no risk of deleting or damaging existing data. Data integrity is paramount. |
| 32 | Never without asking | Deleting or overwriting files, removing accounts. |
| 33 | Expiry alerts | Open question: what K2 offers, and options without K2. |
| 36 | MVP | In: list new books, download, move to NAS, list what is on the NAS. Next: Audiobookshelf check. Out: scheduled digest, removing the Mac. Goal: the Mac is needed only for logins, rarely, so token lifespan matters. |
