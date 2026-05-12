# How-To: Continue Feature Work

**Purpose**: Guide AI agents through resuming work on an active feature

**Scope**: Picking up where a previous session left off; status transitions, branch creation, milestone implementation

**Overview**: Provides the workflow for continuing implementation of an active feature. Covers reading the current state from PROGRESS_TRACKER.md, identifying the next milestone, creating a branch, implementing changes, and updating progress. Handles transitions between planning, active, and completed phases.

**Dependencies**: Feature directory with PROGRESS_TRACKER.md and MILESTONE_BREAKDOWN.md

**Exports**: Completed milestone with updated progress tracking

**Related**: how-to-plan-a-feature.md, how-to-update-progress.md

**Implementation**: Progress-driven continuation with systematic milestone implementation

**Difficulty**: intermediate

---

## Prerequisites

- **Feature directory**: Exists under `.roadmap/features/active/<feature-name>/` (or `planning/` if just starting)
- **PROGRESS_TRACKER.md**: Exists with milestone dashboard
- **MILESTONE_BREAKDOWN.md**: Exists with implementation details

## Steps

### Step 1: Read Feature State

Read these documents in order:

1. `.roadmap/features/active/<feature-name>/PROGRESS_TRACKER.md` - current status and next milestone
2. `.roadmap/features/active/<feature-name>/MILESTONE_BREAKDOWN.md` - implementation details
3. `.roadmap/features/active/<feature-name>/AI_CONTEXT.md` (if exists) - architecture and decisions

### Step 2: Identify Next Milestone

From PROGRESS_TRACKER.md, find:
- The "Next Milestone" section
- Any blocked milestones
- Overall progress status

Inform the user:
```
Feature: <feature-name>
Current progress: X/Y milestones complete
Next milestone: <milestone-title>
Summary: <what this milestone accomplishes>
```

### Step 3: Handle Status Transitions (if needed)

**If feature is in `planning/` and work is beginning**:
```bash
mv .roadmap/features/planning/<feature-name> .roadmap/features/active/<feature-name>
```
Update PROGRESS_TRACKER.md Phase field to "active".

### Step 4: Create Feature Branch

```bash
git checkout -b feat/<feature-name>-milestone-<N>
```

### Step 5: Implement Milestone

Follow the milestone's implementation steps from MILESTONE_BREAKDOWN.md:

1. Read the milestone's detailed steps
2. Implement changes following the documented approach
3. Validate against the milestone's success criteria
4. Run any specified tests or validations

### Step 6: Update Progress

After completing the milestone, follow `.ai/howto/how-to-update-progress.md`:

1. Update PROGRESS_TRACKER.md:
   - Mark milestone status as Complete
   - Add commit hash to Notes: `git log --oneline -1`
   - Update "Next Milestone" section to point to the next incomplete milestone
   - Recalculate overall progress percentage
2. Commit the progress update

### Step 7: Check for Feature Completion

If all milestones are complete:

1. Move feature directory from `active/` to `completed/`:
   ```bash
   mv .roadmap/features/active/<feature-name> .roadmap/features/completed/<feature-name>
   ```
2. Update PROGRESS_TRACKER.md Phase field to "completed"

## Success Criteria

- [ ] Next milestone identified and communicated to user
- [ ] Milestone implemented per MILESTONE_BREAKDOWN.md
- [ ] PROGRESS_TRACKER.md updated with completion status and commit hash
- [ ] Feature branch created for changes
- [ ] Status transitions handled correctly (planning -> active -> completed)
