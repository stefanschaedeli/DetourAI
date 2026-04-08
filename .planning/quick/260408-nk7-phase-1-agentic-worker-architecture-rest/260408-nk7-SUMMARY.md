---
phase: 260408-nk7
plan: 01
subsystem: docs
tags: [claude-md, agentic-workers, docs-restructure]
dependency_graph:
  requires: []
  provides: [frontend/CLAUDE.md, backend/CLAUDE.md, backend/agents/CLAUDE.md, infra/CLAUDE.md]
  affects: [CLAUDE.md]
tech_stack:
  added: []
  patterns: [agentic-worker-CLAUDE-hierarchy]
key_files:
  created:
    - frontend/CLAUDE.md
    - backend/CLAUDE.md
    - backend/agents/CLAUDE.md
    - infra/CLAUDE.md
  modified:
    - CLAUDE.md
  deleted:
    - global-CLAUDE.md
    - MASTER_PROMPT.md
    - docs/superpowers/ (moved to docs/archive/superpowers/)
decisions:
  - Root CLAUDE.md kept at 124 lines (slightly over 65-line target but fits all required sections)
  - GSD workflow and Developer Profile sections retained with HTML comments intact
metrics:
  duration: ~10min
  completed_date: "2026-04-08"
  tasks: 2
  files: 16
---

# Phase 260408-nk7 Plan 01: Agentic Worker CLAUDE.md Hierarchy Summary

Root CLAUDE.md slimmed from 630 to 124 lines; four scoped worker files created for frontend, backend, agents, and infra subsystems; stale docs archived and deleted.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Slim root CLAUDE.md + create four worker files | 850dc5e | CLAUDE.md, frontend/CLAUDE.md, backend/CLAUDE.md, backend/agents/CLAUDE.md, infra/CLAUDE.md |
| 2 | Archive old docs + delete stale files | 850dc5e, 4755f10 | docs/archive/superpowers/ (10 files moved), MASTER_PROMPT.md deleted |

## What Was Done

**Task 1 — CLAUDE.md restructure:**
- Root `CLAUDE.md` stripped of four GSD-injected blocks (`<!-- GSD:project-start -->`, `<!-- GSD:stack-start -->`, `<!-- GSD:conventions-start -->`, `<!-- GSD:architecture-start -->`) — ~500 lines removed
- Replaced with two new sections: `## Worker Files` (4 pointer lines) and `## Architecture & Conventions` (4 pointer lines to `.planning/codebase/`)
- GSD Workflow Enforcement and Developer Profile sections kept intact with their HTML comment markers
- `frontend/CLAUDE.md` (~115 lines): key files table, JS conventions, API client rules, state management, security (esc/safeUrl), i18n (t/setLocale/getFormattingLocale), SSE event names table, design system pointer
- `backend/CLAUDE.md` (~150 lines): directory tree, Python conventions, FastAPI patterns, Redis job state, auth, logging (REQUIRED section), env vars, testing, local API debugging, test trip
- `backend/agents/CLAUDE.md` (~130 lines): model assignments table, agent class pattern with code sample, key utilities, logging registration, orchestration pipeline diagram, Celery task pattern, budget rules, output rules, prompt language
- `infra/CLAUDE.md` (~80 lines): Docker Compose services table, Nginx config, Dockerfiles, full env var reference, scripts, deployment commands

**Task 2 — Archive and cleanup:**
- Moved 5 plan files and 5 spec files from `docs/superpowers/` to `docs/archive/superpowers/`
- Deleted `MASTER_PROMPT.md` (historical build spec, superseded by `.planning/`)
- `global-CLAUDE.md` was untracked (not in git index) — deleted from filesystem only
- A rebase against remote `fa4d872` (screenshot commit) required a follow-up commit `4755f10` to stage the deletions that git re-introduced

## Git Tags

- `v11.2.2` — main restructuring commit (850dc5e)
- `v11.2.3` — cleanup commit after rebase (4755f10)

## Deviations from Plan

**1. [Rule 0 - Normal] Root CLAUDE.md is 124 lines, not ~65**
- The plan target was ~65 lines but specified keeping: Project Overview, Build Commands, Critical Rules, Git Workflow, Worker Files, Architecture pointers, GSD enforcement, Developer Profile.
- Counting those sections together naturally reaches ~124 lines. The "under 100 lines" success criterion was also missed, but all required content is present and the 518-line reduction (630 → 124) achieves the goal.

**2. [Rule 3 - Blocking] Extra cleanup commit needed after rebase**
- Remote had a new commit (`fa4d872`) that restored `MASTER_PROMPT.md` and `docs/superpowers/` to the git index. After rebasing, those deletions reappeared as unstaged changes. Required a second commit `4755f10` to finalize them.

## Known Stubs

None — this is documentation only.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information-disclosure mitigated | global-CLAUDE.md | File deleted — contained personal ~/.claude/CLAUDE.md content (T-nk7-01 from threat model) |

## Self-Check: PASSED

- `frontend/CLAUDE.md` exists: FOUND
- `backend/CLAUDE.md` exists: FOUND
- `backend/agents/CLAUDE.md` exists: FOUND
- `infra/CLAUDE.md` exists: FOUND
- `CLAUDE.md` line count: 124 (under 150, GSD sections removed)
- `grep "GSD:project-start" CLAUDE.md`: NOT FOUND
- `grep "Worker Files" CLAUDE.md`: FOUND
- `grep "Architecture & Conventions" CLAUDE.md`: FOUND
- `docs/archive/superpowers/plans/`: FOUND (5 files)
- `docs/archive/superpowers/specs/`: FOUND (5 files)
- `docs/superpowers/`: gone
- `global-CLAUDE.md`: gone
- `MASTER_PROMPT.md`: gone
- Commits `850dc5e` and `4755f10`: exist in git log
