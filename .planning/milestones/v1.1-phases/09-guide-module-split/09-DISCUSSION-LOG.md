# Phase 9: Guide Module Split - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 09-guide-module-split
**Areas discussed:** Module boundaries, Shared state strategy, Edit operations placement, Load order & dependencies

---

## Module Boundaries

| Option | Description | Selected |
|--------|-------------|----------|
| 7 modules looks good | guide-core, guide-overview, guide-stops, guide-days, guide-map, guide-edit, guide-share — each focused on one concern | ✓ |
| Merge share into core | guide-share is only ~70 lines. Fold it into guide-core to avoid a tiny standalone file (6 modules total) | |
| Merge share into edit | Share toggle is part of the editing/management area. Fold into guide-edit (6 modules total) | |

**User's choice:** 7 modules looks good
**Notes:** User accepted the proposed 7-module split without modification. Function allocation table presented with approximate line counts per module.

---

## Shared State Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Each module owns its state | Map state lives in guide-map.js, edit state in guide-edit.js. Navigation state in guide-core.js. Modules export getters/setters for cross-module access. | ✓ |
| Central GuideState object | Create a single GuideState = {} in guide-core.js. All modules read/write through it. | |
| Extend existing S object | Add guide-specific state to the existing global S object in state.js. | |

**User's choice:** Each module owns its state (Recommended)
**Notes:** Navigation state (activeTab, _activeStopId, _activeDayNum) centralized in guide-core since multiple modules read it.

---

## Edit Operations Placement

| Option | Description | Selected |
|--------|-------------|----------|
| In guide-edit.js | SSE handlers are part of the edit workflow. They call into guide-core and guide-map as cross-module calls. | ✓ |
| In guide-core.js | SSE handlers are response processors, not edit initiators. Placing them in core keeps event flow centralized. | |

**User's choice:** In guide-edit.js (Recommended)
**Notes:** All 5 SSE edit-complete handlers stay with the editing logic they conclude.

---

## Load Order & Dependencies

| Option | Description | Selected |
|--------|-------------|----------|
| Flat globals | Keep same pattern as rest of app. Functions stay as global names. Load order: core → overview → stops → days → map → edit → share. | ✓ |
| Guide namespace object | Create window.Guide = {}. Each module registers Guide.overview.render(), etc. Cleaner but breaks call sites. | |
| Minimal namespace for internals only | Public API stays flat globals. Only cross-module internal calls use shared object. | |

**User's choice:** Flat globals (Recommended)
**Notes:** Consistent with existing codebase. No changes to call sites in router.js, progress.js, etc.

---

## Claude's Discretion

- Exact line-level cut points within guide.js for each function
- Whether _private helper functions move with their primary consumer or stay closer to callers
- Header comment format and level of detail

## Deferred Ideas

None — discussion stayed within phase scope
