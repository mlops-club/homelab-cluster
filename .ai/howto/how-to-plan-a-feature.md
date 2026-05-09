# How-To: Plan a Feature

**Purpose**: Guide AI agents through planning a new feature with the three-document roadmap structure

**Scope**: Feature planning from discovery through document creation; does not cover implementation

**Overview**: Walks through the process of planning a new feature using the roadmap pattern. Creates a feature directory with PROGRESS_TRACKER.md, MILESTONE_BREAKDOWN.md, and AI_CONTEXT.md from templates. Helps agents gather requirements, break work into milestones, and validate the plan.

**Dependencies**: .ai/ directory with templates, .roadmap/features/ directory structure

**Exports**: Complete feature planning directory with three documents ready for implementation

**Related**: how-to-continue-feature-work.md, how-to-update-progress.md

**Implementation**: Template-based planning with guided discovery questions

**Difficulty**: intermediate

---

## Prerequisites

- **Repository**: Has .ai/ directory with templates
- **Roadmap directory**: `.roadmap/features/` exists with `planning/`, `active/`, `completed/` subdirectories
- **Templates**: Feature templates exist in `.ai/templates/`
  - `feature-progress-tracker.md.template`
  - `feature-milestone-breakdown.md.template`
  - `feature-ai-context.md.template`

## Steps

### Step 1: Gather Feature Information

Ask the user (or infer from context):

1. **Feature Name**: What is this feature called? (use kebab-case for directory name)
2. **Feature Scope**: What does this feature accomplish? What is explicitly out of scope?
3. **Feature Vision**: What is the desired end state?
4. **Dependencies**: What does this feature depend on? (other features, infrastructure, external services)
5. **Success Criteria**: How do you know the feature is done?

### Step 2: Create Feature Directory

```bash
mkdir -p .roadmap/features/planning/<feature-name>/
```

Replace `<feature-name>` with the kebab-case name from Step 1.

### Step 3: Create the Three Documents

Copy templates and replace all `{{PLACEHOLDERS}}` with actual values from Step 1.

**PROGRESS_TRACKER.md** (primary AI handoff document):
```bash
cp .ai/templates/feature-progress-tracker.md.template .roadmap/features/planning/<feature-name>/PROGRESS_TRACKER.md
```

**MILESTONE_BREAKDOWN.md** (detailed implementation guide):
```bash
cp .ai/templates/feature-milestone-breakdown.md.template .roadmap/features/planning/<feature-name>/MILESTONE_BREAKDOWN.md
```

**AI_CONTEXT.md** (feature context and architecture):
```bash
cp .ai/templates/feature-ai-context.md.template .roadmap/features/planning/<feature-name>/AI_CONTEXT.md
```

### Step 4: Break Into Milestones

Work with the user to identify milestones:

- Each milestone should be self-contained and testable
- Milestones should build incrementally toward the feature
- Each milestone should be completable in a single session
- Consider dependencies between milestones
- Order milestones so earlier ones create foundation for later ones

Fill the milestones into MILESTONE_BREAKDOWN.md with:
- Implementation steps for each milestone
- File changes expected
- Testing requirements
- Success criteria

### Step 5: Populate PROGRESS_TRACKER.md

Fill in:
- Milestone dashboard with all milestones from Step 4
- "Next Milestone" section pointing to Milestone 1
- Pre-flight checklist for Milestone 1
- Definition of done from Step 1

### Step 6: Validate

- [ ] Feature directory exists at `.roadmap/features/planning/<feature-name>/`
- [ ] PROGRESS_TRACKER.md exists with milestone dashboard and next-milestone section
- [ ] MILESTONE_BREAKDOWN.md exists with detailed milestone steps
- [ ] AI_CONTEXT.md exists with feature vision, scope, and architecture
- [ ] All `{{PLACEHOLDERS}}` replaced with actual values

### Step 7: Inform User

Present the feature plan to the user:
- Summary of milestones identified
- Estimated scope and complexity
- Recommended starting point
- Ask if they want to begin implementation (which moves the feature to `active/`)

## Next Steps

When ready to implement:
1. Move feature directory from `planning/` to `active/`
2. Follow `.ai/howto/how-to-continue-feature-work.md`
3. Create a feature branch for the first milestone

## Success Criteria

- [ ] Three documents created with feature-specific content
- [ ] Milestones are well-defined and sequenced
- [ ] User has reviewed and approved the plan
