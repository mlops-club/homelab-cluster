# How-To: Update Progress

**Purpose**: Guide AI agents through updating progress on features

**Scope**: Updating PROGRESS_TRACKER.md after completing work

**Overview**: Covers the standard process for recording progress after completing milestones or features. Ensures consistent tracking with commit hashes, status updates, progress recalculation, and phase transitions.

**Dependencies**: Active feature with tracking documents

**Exports**: Updated progress tracking documents

**Related**: how-to-continue-feature-work.md, how-to-plan-a-feature.md

**Implementation**: Systematic progress recording with commit hash tracking

**Difficulty**: beginner

---

## Prerequisites

- **Tracking document**: PROGRESS_TRACKER.md exists for the feature
- **Completed work**: A milestone has been completed

## Updating Feature Progress

### Step 1: Update Milestone Status

Open `.roadmap/features/<phase>/<feature-name>/PROGRESS_TRACKER.md`.

In the Milestone Dashboard table:
1. Change the completed milestone's Status to Complete
2. Add commit hash to Notes column:
   ```bash
   git log --oneline -1
   ```
3. Format: "Description (commit abc1234)"

### Step 2: Update Next Milestone Section

Update the "Next Milestone" section in PROGRESS_TRACKER.md:
- Point to the next incomplete milestone
- Update the pre-flight checklist for that milestone
- If all milestones are complete, note "Feature Complete"

### Step 3: Recalculate Progress Percentage

Calculate: `(completed milestones / total milestones) * 100`

Update both the progress bar and the percentage display.

### Step 4: Commit Progress Update

```bash
git add .roadmap/features/<phase>/<feature-name>/PROGRESS_TRACKER.md
git commit -m "docs: update progress for <feature-name> milestone <N>"
```

## Handling Phase Transitions

### Feature: planning -> active

When implementation begins:
```bash
mv .roadmap/features/planning/<feature-name> .roadmap/features/active/<feature-name>
```
Update PROGRESS_TRACKER.md Phase field to "active".

### Feature: active -> completed

When all milestones are done:
```bash
mv .roadmap/features/active/<feature-name> .roadmap/features/completed/<feature-name>
```
Update PROGRESS_TRACKER.md Phase field to "completed".

## Success Criteria

- [ ] Progress tracking document updated with current status
- [ ] Commit hash recorded for completed work
- [ ] Next action/milestone correctly identified
- [ ] Progress percentage accurately calculated
- [ ] Phase transitions handled when applicable
