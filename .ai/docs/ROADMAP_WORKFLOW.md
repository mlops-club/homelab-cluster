# Roadmap Workflow Documentation

**Purpose**: Comprehensive documentation of the roadmap-driven development workflow

**Scope**: Feature lifecycle, document structure, AI agent coordination

**Overview**: Technical documentation for the roadmap system used in this repository.
    Describes the feature document structures, lifecycle management
    (planning -> active -> completed), AI agent handoff protocols, and workflow patterns.

**Dependencies**: .ai/templates/ for feature templates, .roadmap/ directory structure

**Exports**: Workflow patterns, coordination protocols, lifecycle management guidelines

**Related**: howto guides for planning and continuing work, roadmap templates, AGENTS.md

**Implementation**: Lifecycle-based workflow with structured handoff documentation

---

## Overview

The roadmap workflow provides a structured system for planning and tracking work:

**Features** - Individual deliverables with milestones

Features follow the lifecycle: `planning/` -> `active/` -> `completed/`

## Feature Structure

Each feature uses three documents:

### 1. PROGRESS_TRACKER.md (Required)
**Role**: Primary AI agent handoff document

Contains:
- Current status and next milestone
- Overall progress dashboard
- Milestone status table
- Update protocol

This is the FIRST document AI agents read when continuing work.

### 2. MILESTONE_BREAKDOWN.md (Required for multi-milestone features)
**Role**: Detailed implementation guide

Contains:
- Milestone breakdown with implementation steps
- Success criteria for each milestone
- Dependencies between milestones

### 3. AI_CONTEXT.md (Optional)
**Role**: Feature architecture context

Contains:
- Feature vision and rationale
- Target architecture
- Key decisions
- AI agent guidance

## Lifecycle

### Planning Phase
**Location**: `.roadmap/features/planning/`

Activities:
1. Create directory with three documents
2. Fill in templates with specifics
3. Break work into milestones
4. Define success criteria
5. Review and refine plan

### Active Phase
**Location**: `.roadmap/features/active/`

Activities:
1. Read PROGRESS_TRACKER.md to identify next action
2. Implement milestone
3. Update tracking documents
4. Continue until complete

### Completed Phase
**Location**: `.roadmap/features/completed/`

Purpose:
- Archive for reference
- Extract learnings
- Inform future planning

## AI Agent Coordination

### Feature Work Flow

```
1. Read PROGRESS_TRACKER.md
2. Identify next milestone
3. Read MILESTONE_BREAKDOWN.md for that milestone
4. Create feature branch
5. Implement milestone
6. Update PROGRESS_TRACKER.md
7. Commit changes
```

### Detection Patterns

AI agents detect roadmap requests through:

**Feature planning**: "plan feature", "roadmap", "break down"
**Continuation**: "continue", "resume", "next milestone"
**Progress updates**: "update progress", "mark complete"

## Templates

### Feature Templates
- `feature-progress-tracker.md.template` - Primary handoff document
- `feature-milestone-breakdown.md.template` - Milestone implementation details
- `feature-ai-context.md.template` - Feature architecture context

## Best Practices

### Planning
- Break features into atomic milestones (each independently testable)
- Define clear success criteria for each milestone
- Use AI_CONTEXT.md for complex features with architecture decisions
- Map dependencies explicitly

### Implementation
- Read PROGRESS_TRACKER.md before every work session
- Update tracking documents immediately after completing milestones
- Document deviations and reasons
- Test thoroughly per success criteria

### Completion
- Move directories to completed/ when all work is done
- Preserve documents for future reference
- Extract reusable patterns

## Integration

### With AGENTS.md
Roadmap section in AGENTS.md provides detection patterns and routing.

### With .ai/index.yaml
Roadmap resources registered under the `roadmap:` section.

### With Templates
Feature templates in `.ai/templates/` enable consistent planning.
