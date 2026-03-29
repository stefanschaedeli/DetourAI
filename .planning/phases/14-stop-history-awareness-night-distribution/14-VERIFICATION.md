---
phase: 14-stop-history-awareness-night-distribution
verified: 2026-03-29T00:00:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 14: Stop History Awareness + Night Distribution Verification Report

**Phase Goal:** Stop history awareness and night distribution — prevent duplicate stop suggestions and show remaining night budget
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | StopOptionsFinder prompt contains KRITISCH exclusion rule listing already-selected stops | VERIFIED | `stop_options_finder.py` line 78-83: `"KRITISCH — Duplikat-Vermeidung: Schlage KEINEN der folgenden bereits ausgewählten Stopps erneut vor: "` + excluded_names using full selected_stops |
| 2 | When more than 8 stops are selected, prompt shows only last 5 with count summary | VERIFIED | `stop_options_finder.py` lines 58-73: `MAX_HISTORY_FULL = 8`, `TAIL_COUNT = 5`, capped_stops = selected_stops[-TAIL_COUNT:], history_prefix shows count |
| 3 | Post-processing in _enrich_one silently drops options whose region matches a selected stop (case-insensitive) | VERIFIED | `main.py` lines 847-856: `opt_region = opt.get("region", "").lower()`, set comprehension `already_selected`, `if opt_region in already_selected: return None` |
| 4 | All 3 _find_and_stream_options call sites pass architect_context | VERIFIED | `main.py` lines 1382, 1492, 1573: all three have `architect_context=job.get("architect_plan"),` |
| 5 | Meta response from select_stop and recompute_options includes nights_remaining field | VERIFIED | `main.py` lines 1399, 1507, 1587: `"nights_remaining": new_status["nights_remaining"]` / `route_status["nights_remaining"]` in all three meta dicts |
| 6 | Architect plan's recommended_nights is injected per-stop based on position in regions list | VERIFIED | `stop_options_finder.py` lines 153-164: position index math `int((stop_number-1)/max(1,estimated_total)*len(regions))`, appends `"FÜR DIESEN STOP: Empfehle {rec_nights} Nächte"` |
| 7 | User sees "X Nächte verbleibend" in route builder status during stop selection | VERIFIED | `route-builder.js` lines 339-344: `nightsRem` extracted from `meta.nights_remaining`, `budgetInfo = "${nightsRem} Nächte · ${daysRem} Tage verbleibend"`, set via `subtitle.textContent` |
| 8 | Night budget display updates dynamically as stops are selected | VERIFIED | `_updateRouteStatus(meta)` reads `meta.nights_remaining` on every call; meta is provided by both select_stop and recompute_options responses |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/stop_options_finder.py` | KRITISCH exclusion rule, history capping, per-stop nights recommendation | VERIFIED | Contains all three features at lines 58-83 (capping+exclusion) and 153-164 (per-stop nights) |
| `backend/main.py` | Post-processing dedup in _enrich_one, architect_context wiring, nights_remaining in meta | VERIFIED | Dedup at line 847-856, three architect_context wires at 1382/1492/1573, nights_remaining in _calc_route_status (line 273) and all three meta dicts |
| `backend/tests/test_agents_mock.py` | Tests for exclusion rule, history capping, and dedup | VERIFIED | Three test functions at lines 1152, 1173, 1192: test_stop_options_exclusion_rule, test_stop_history_cap, test_stop_options_nights_recommendation — all pass |
| `frontend/js/route-builder.js` | Nights remaining display in route status subtitle | VERIFIED | `meta.nights_remaining` read at line 339, budgetInfo at 340-342, textContent assignment at 344 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `stop_options_finder.py` | prompt template | exclusion_rule inserted between stops_str and geo_block | WIRED | Line 272: `{stops_str}{exclusion_rule}` in return f-string template |
| `main.py _enrich_one` | selected_stops closure | case-insensitive region match | WIRED | `already_selected` set built from closure `selected_stops` at line 849; match at 850 |
| `main.py select_stop (segment transition)` | `_find_and_stream_options` | `architect_context=job.get("architect_plan")` | WIRED | Line 1382 |
| `main.py select_stop (continue-building)` | `_find_and_stream_options` | `architect_context=job.get("architect_plan")` | WIRED | Line 1492 |
| `main.py recompute_options` | `_find_and_stream_options` | `architect_context=job.get("architect_plan")` | WIRED | Line 1573 |
| `route-builder.js _updateRouteStatus` | `meta.nights_remaining` | reads nights_remaining from meta with daysRem-1 fallback | WIRED | Line 339: `(meta.nights_remaining != null) ? meta.nights_remaining : (daysRem > 0 ? daysRem - 1 : 0)` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `route-builder.js _updateRouteStatus` | `nightsRem` | `meta.nights_remaining` from API response (select_stop / recompute_options) | Yes — `_calc_route_status` computes `max(0, days_remaining - 1)` from real job state | FLOWING |
| `stop_options_finder.py _build_prompt` | `exclusion_rule` | `selected_stops` list passed by caller | Yes — caller passes job["selected_stops"] from Redis job state | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| KRITISCH exclusion rule present in prompt | `grep -n "KRITISCH.*Duplikat" backend/agents/stop_options_finder.py` | Line 78 match | PASS |
| architect_context wired at all 3 call sites | `grep -n "architect_context=job.get" backend/main.py \| wc -l` | 3 matches | PASS |
| nights_remaining in _calc_route_status and meta dicts | `grep -n "nights_remaining" backend/main.py` | Lines 273, 1399, 1507, 1587 | PASS |
| Post-processing dedup in _enrich_one | `grep -n "opt_region in already_selected" backend/main.py` | Line 850 | PASS |
| 3 new tests pass | `python3 -m pytest tests/test_agents_mock.py -k "exclusion_rule or history_cap or nights_recommendation" -v` | 3 passed | PASS |
| Full test suite passes | `python3 -m pytest tests/ -v` | 307 passed, 1 warning | PASS |
| nights_remaining in route-builder.js | `grep -n "nights_remaining" frontend/js/route-builder.js` | Line 339 | PASS |
| "Nächte" display string present | `grep -n "Nächte" frontend/js/route-builder.js` | Line 341: `${nightsRem} Nächte · ${daysRem} Tage verbleibend` | PASS |
| Fallback for backward compat | `grep -n "daysRem - 1" frontend/js/route-builder.js` | Line 339 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RTE-03 | 14-01, 14-02 | StopOptionsFinder kennt alle bisherigen Stops und schlägt keine Duplikate vor | SATISFIED | KRITISCH exclusion rule in prompt (all stops), history capping for context display, post-processing dedup in _enrich_one — three layers of duplicate prevention |
| RTE-04 | 14-01, 14-02 | Post-Processing Dedup verhindert doppelte Städte als Safety Net | SATISFIED | `_enrich_one` in `main.py` lines 847-856 does case-insensitive region match against selected_stops closure and returns None for duplicates; logged at DEBUG level |

Both requirements mapped in REQUIREMENTS.md to Phase 14. No orphaned requirements found.

### Anti-Patterns Found

No blockers or warnings found.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | — |

Scan of modified files (`stop_options_finder.py`, `main.py`, `route-builder.js`, `test_agents_mock.py`) found no TODO/FIXME placeholders, no empty handlers, no hardcoded empty data arrays in paths that flow to rendering, no return null stubs. The `return None` in `_enrich_one` is intentional rejection logic (not a stub).

### Human Verification Required

#### 1. Visual Night Budget Display During Route Building

**Test:** Start a trip planning session, enter the route-building phase, and select a stop.
**Expected:** Subtitle under the route-builder heading shows a string like "3 Nächte · 4 Tage verbleibend" that decreases as more stops are added.
**Why human:** `subtitle.textContent` set correctly in code, but the actual DOM rendering and meta delivery over SSE can only be validated in a running browser session.

#### 2. Duplicate Prevention in Live Session

**Test:** Begin route building, select a stop (e.g. "Colmar"), continue selecting more stops, and observe whether "Colmar" ever reappears as a suggested option.
**Expected:** Colmar should never appear again in subsequent option lists — filtered both at prompt level (KRITISCH rule) and post-processing (dedup in _enrich_one).
**Why human:** Both filtering layers depend on the AI model honouring the KRITISCH rule and on live API responses — cannot be verified without a running Anthropic session.

### Gaps Summary

No gaps. All must-haves verified at all levels.

Both requirement IDs (RTE-03 and RTE-04) are fully satisfied. Three layers of duplicate prevention are in place: prompt-level KRITISCH rule, history context capping, and post-processing dedup. Night distribution is wired end-to-end from `_calc_route_status` through all meta response paths to the route-builder UI. All 307 tests pass. All 3 commits (cd22a6d, 2be63f2, 7b953e4) are present in git history.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
