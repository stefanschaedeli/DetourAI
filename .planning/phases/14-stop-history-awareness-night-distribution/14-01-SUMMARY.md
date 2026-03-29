---
phase: 14-stop-history-awareness-night-distribution
plan: "01"
subsystem: backend-agents
tags: [stop-options-finder, dedup, night-distribution, architect-context]
dependency_graph:
  requires: []
  provides: [KRITISCH-exclusion-rule, history-capping, per-stop-nights, post-processing-dedup, architect-context-wiring, nights-remaining-meta]
  affects: [backend/agents/stop_options_finder.py, backend/main.py]
tech_stack:
  added: []
  patterns: [prompt-level-exclusion-rule, closure-based-dedup, position-based-nights-recommendation]
key_files:
  created: []
  modified:
    - backend/agents/stop_options_finder.py
    - backend/main.py
    - backend/tests/test_agents_mock.py
decisions:
  - "exclusion_rule uses full selected_stops (not capped) so old stops are still excluded even when history display is capped"
  - "per-stop nights uses position-based index math: int((stop_number-1)/estimated_total * len(regions))"
  - "nights_remaining = max(0, days_remaining - 1) — simple formula, covers the common case"
metrics:
  duration_minutes: 8
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_changed: 3
requirements: [RTE-03, RTE-04]
---

# Phase 14 Plan 01: Stop History Awareness + Night Distribution Summary

Backend dedup and night distribution for StopOptionsFinder: KRITISCH prompt-level exclusion rule, history capping to last 5 when >8 stops, per-stop nights from architect plan position, post-processing dedup in `_enrich_one`, architect_context wiring at all 3 call sites, and `nights_remaining` in all meta responses.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | KRITISCH exclusion rule, history capping, per-stop nights | cd22a6d | backend/agents/stop_options_finder.py |
| 2 | Post-processing dedup, architect_context wiring, nights_remaining, tests | 2be63f2 | backend/main.py, backend/tests/test_agents_mock.py |

## Changes Made

### Task 1 — stop_options_finder.py

Added to `_build_prompt()`:

1. **History capping (D-09):** `MAX_HISTORY_FULL = 8` / `TAIL_COUNT = 5`. When >8 stops selected, `stops_str` shows only the last 5 with a count prefix ("10 bisherige Stopps, letzte 5: ..."). The `exclusion_rule` still uses the full list.

2. **KRITISCH exclusion rule (D-01, D-02):** Builds `exclusion_rule` from ALL selected stops and inserts it into the prompt template between `{stops_str}` and `{geo_block}`. Text: "KRITISCH — Duplikat-Vermeidung: Schlage KEINEN der folgenden bereits ausgewählten Stopps erneut vor: ..."

3. **Per-stop nights recommendation (D-06, D-07):** Enhanced the `architect_block` with position-based current region lookup. Uses `int((stop_number-1) / max(1, estimated_total) * len(regions))` to find the relevant region and appends "FÜR DIESEN STOP: Empfehle N Nächte (basierend auf Potential der Region X)."

### Task 2 — main.py + tests

1. **Post-processing dedup in `_enrich_one`:** After coords validation, builds `already_selected` set from closure `selected_stops` and returns `None` if `opt_region in already_selected`. Logs at DEBUG level.

2. **architect_context wiring:** Added `architect_context=job.get("architect_plan"),` to all 3 `_find_and_stream_options` call sites:
   - select_stop segment transition (~line 1370)
   - select_stop continue-building (~line 1478)
   - recompute_options (~line 1557)

3. **nights_remaining in `_calc_route_status`:** Added `"nights_remaining": max(0, days_remaining - 1)` to the return dict. Propagated into meta dicts in all 3 response paths.

4. **3 new tests:**
   - `test_stop_options_exclusion_rule` — RTE-03: KRITISCH + Duplikat-Vermeidung present with stop names
   - `test_stop_history_cap` — RTE-03: count summary when >8 stops, exclusion rule lists ALL stops
   - `test_stop_options_nights_recommendation` — D-07: FÜR DIESEN STOP present with correct region

## Verification

```
grep -n "KRITISCH.*Duplikat" backend/agents/stop_options_finder.py  → line 79
grep -n "architect_context=job.get" backend/main.py | wc -l          → 3
grep -n "nights_remaining" backend/main.py                             → lines 273, 1399, 1507, 1587
grep -n "opt_region in already_selected" backend/main.py              → line 850
python3 -m pytest tests/ -v                                           → 305 passed, 2 pre-existing failures
```

## Deviations from Plan

None — plan executed exactly as written. The 2 test failures in `test_endpoints.py` are pre-existing (ANTHROPIC_API_KEY not set in test environment) and unrelated to this plan.

## Known Stubs

None.

## Self-Check: PASSED

Files verified:
- backend/agents/stop_options_finder.py — FOUND, contains KRITISCH
- backend/main.py — FOUND, contains nights_remaining and opt_region in already_selected
- backend/tests/test_agents_mock.py — FOUND, contains 3 new test functions

Commits verified:
- cd22a6d — FOUND (feat(14-01): KRITISCH exclusion rule...)
- 2be63f2 — FOUND (feat(14-01): post-processing dedup...)
