---
phase: 15-hotel-geheimtipp-quality-day-plan-recalculation
plan: "01"
subsystem: backend/agents
tags: [accommodation, geheimtipp, quality, haversine, dedup]
dependency_graph:
  requires: []
  provides: [geheimtipp-distance-filter, name-dedup, prompt-coordinate-hint]
  affects: [backend/agents/accommodation_researcher.py, backend/tests/test_agents_mock.py]
tech_stack:
  added: []
  patterns: [haversine distance check, name-based dedup, prompt coordinate anchoring]
key_files:
  created: []
  modified:
    - backend/agents/accommodation_researcher.py
    - backend/tests/test_agents_mock.py
decisions:
  - "Haversine filter applied post-gather, not inside enrich_option return — ensures all enrichment runs first, then filtered options are clean"
  - "Name dedup applied after haversine filter to minimize wasted work"
  - "No false rejection: Geheimtipps without gp_match pass through unconditionally"
  - "Non-geheimtipp options are never subject to distance filter"
metrics:
  duration: "6min"
  completed: "2026-03-29"
  tasks: 1
  files: 2
---

# Phase 15 Plan 01: Geheimtipp Distance Filter + Name Dedup Summary

**One-liner:** Haversine post-filter drops Geheimtipp hotels beyond hotel_radius_km; case-insensitive name dedup removes duplicates; prompt includes explicit stop coordinates for Claude anchoring.

## What Was Built

### D-01 — Prompt coordinate hint
Added `coord_hint` to `find_options()` prompt. When `lat` and `lon` are available for the stop, the prompt now includes:
```
Stopzentrum: 45.8990N, 6.1290E — alle Unterkuenfte muessen innerhalb von 25 km davon liegen.
```
This gives Claude a concrete geographic anchor to prevent recommending distant hotels.

### D-02 — Haversine post-filter (ACC-01)
Inside `enrich_option()`, after `gp_match` is determined: if the option is a Geheimtipp AND has a gp_match with lat/lon, compute `haversine_km(stop_center, gp_match)`. If distance exceeds `req.hotel_radius_km`, set `_geheimtipp_too_far = True`. After `asyncio.gather`, filter those out silently.

Guard conditions (no false rejection):
- Non-geheimtipp options: never filtered
- Geheimtipp without gp_match: no lat/lon available → passes through

### D-04 — Name-based dedup (ACC-02)
After the haversine filter, iterate options maintaining a `seen_names` set (lowercased, stripped). First occurrence of each name is kept; subsequent duplicates are dropped. Options without a name are always kept.

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Prompt enhancement + haversine filter + dedup | 8088c49 | accommodation_researcher.py, test_agents_mock.py |

## Test Results

- 6 new tests added and passing:
  - `test_geheimtipp_distance_filter` — far Geheimtipp (50km > 25km radius) is dropped
  - `test_geheimtipp_close_passes_through` — near Geheimtipp (5km < 25km radius) is kept
  - `test_geheimtipp_no_gp_match_passes_through` — Geheimtipp without gp_match is never dropped
  - `test_non_geheimtipp_never_dropped` — non-Geheimtipp options are never filtered
  - `test_geheimtipp_dedup` — same name (case-insensitive) deduplicated to one entry
  - `test_dedup_different_names_all_kept` — different names all kept (no false dedup)
- Full `test_agents_mock.py`: 55/55 passing
- Pre-existing failures (`test_plan_trip_success`, `test_research_accommodation_success`) require `ANTHROPIC_API_KEY` env var — confirmed pre-existing, not introduced by this plan

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- `backend/agents/accommodation_researcher.py` — exists and contains `haversine_km`, `Stopzentrum`, `_geheimtipp_too_far`, `seen_names`
- `backend/tests/test_agents_mock.py` — contains `test_geheimtipp_distance_filter`, `test_geheimtipp_dedup`
- Commit `8088c49` — present in git log
