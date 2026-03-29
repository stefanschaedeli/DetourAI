# Phase 14: Stop History Awareness + Night Distribution - Research

**Researched:** 2026-03-29
**Domain:** Prompt engineering + post-processing dedup + frontend night budget display
**Confidence:** HIGH

## Summary

Phase 14 is a focused improvement to StopOptionsFinder with three distinct concerns: (1) prompt-level dedup via a KRITISCH exclusion rule, (2) post-processing dedup as a safety net in `_find_and_stream_options`, and (3) a "Nächte verbleibend" indicator in the frontend. All decisions have been locked by the CONTEXT.md discussion — no architectural research is needed, only precise implementation knowledge.

The entire change set stays within four files: `backend/agents/stop_options_finder.py` (prompt modification), `backend/main.py` (`_find_and_stream_options` dedup + architect_context wiring in `select_stop`), and `frontend/js/route-builder.js` (nights remaining UI). There are no new dependencies, no new agent files, and no schema changes.

**Primary recommendation:** Add the KRITISCH exclusion rule directly after the `stops_str` line in `_build_prompt()`, cap the history at the last 5 stops when length exceeds 8, add the dedup check inside `_enrich_one()` before proximity filtering (consistent with existing silent-reject pattern), and wire `architect_context=job.get("architect_plan")` into all four `_find_and_stream_options` call sites in `select_stop` and `recompute_options`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Add a KRITISCH exclusion rule to the StopOptionsFinder system prompt or user prompt: "Schlage KEINE Orte vor die bereits als Stopp ausgewählt wurden." Leverages the existing `stops_str` listing of bisherige Stopps.

**D-02:** No separate blocklist block needed — the existing "Bisherige Stopps: ..." line combined with the new exclusion rule is sufficient.

**D-03:** Case-insensitive exact match on `region` name against `selected_stops`. Matches the existing confirm-route dedup pattern (main.py line 1740).

**D-04:** When a duplicate is detected in returned options, silently drop it. User sees fewer than 3 options — simple and honest. No retry for replacement.

**D-05:** Post-processing dedup runs in `_find_and_stream_options` after each option is enriched, before the SSE event is pushed.

**D-06:** StopOptionsFinder's JSON output includes a `recommended_nights` field pre-filled from the architect plan's region recommendation. User still picks final nights during stop selection, but the default matches the plan.

**D-07:** Night recommendations from the architect plan are injected more prominently — not just as context but as a suggested default in the prompt (e.g., "Empfehle für diese Region X Nächte basierend auf dem Architect-Plan").

**D-08:** Frontend displays "X Nächte verbleibend" alongside stop options during route building. The backend already tracks `days_remaining` — extend this to expose a night-specific balance.

**D-09:** Cap stop history in the prompt. If more than 8 stops are selected, include only the last 5 plus a count summary (e.g., "8 bisherige Stopps, letzte 5: ..."). Prevents unbounded prompt growth on long trips.

### Claude's Discretion

- Exact wording of the KRITISCH exclusion rule in German
- Where exactly in the prompt the exclusion rule is placed (system prompt vs user prompt)
- Exact threshold for history capping (suggested 8/5 but Claude can adjust based on token analysis)
- How `recommended_nights` is derived when the current region doesn't exactly match an architect plan region (fuzzy matching strategy)
- UI placement and styling of the "Nächte verbleibend" indicator

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RTE-03 | StopOptionsFinder kennt alle bisherigen Stops und schlägt keine Duplikate vor | D-01 + D-02: KRITISCH rule in `_build_prompt()` referencing existing `stops_str`; D-09: history capping |
| RTE-04 | Post-Processing Dedup verhindert doppelte Städte als Safety Net | D-03 + D-04 + D-05: case-insensitive `region` match inside `_find_and_stream_options._enrich_one()`, silent drop |
</phase_requirements>

---

## Standard Stack

No new libraries. All changes use existing project patterns.

| Component | File | Pattern | Source |
|-----------|------|---------|--------|
| Prompt exclusion rule | `stop_options_finder.py` `_build_prompt()` | KRITISCH rule after `stops_str` (same as existing geography/drive KRITISCH rules) | Code audit — HIGH |
| Post-processing dedup | `main.py` `_find_and_stream_options._enrich_one()` | Return `None` to silently reject (same as proximity + corridor checks) | Code audit — HIGH |
| `architect_context` wiring | `main.py` `select_stop` + `recompute_options` | `job.get("architect_plan")` already stored from Phase 13 | Code audit — HIGH |
| Night budget UI | `route-builder.js` `_updateRouteStatus()` | Append to `subtitle` text alongside existing "X Tage verbleibend" | Code audit — HIGH |

---

## Architecture Patterns

### Existing KRITISCH Rule Pattern (stop_options_finder.py SYSTEM_PROMPT)

The SYSTEM_PROMPT already has three KRITISCH rules. The new exclusion rule belongs in the **user prompt** (not SYSTEM_PROMPT) because it references dynamic per-request data (the actual selected stop names). The natural insertion point is immediately after the `stops_str` block.

```python
# Current stops_str block (lines 58-64 in stop_options_finder.py)
stops_str = ""
if selected_stops:
    parts = [
        f"Stop {s['id']}: {s['region']} ({s.get('country','?')}, ...)"
        for s in selected_stops
    ]
    stops_str = "Bisherige Stopps: " + ", ".join(parts) + "\n"

# D-01: Exclusion rule appended immediately after stops_str
# D-09: Cap to last 5 when len > 8
```

The exclusion rule text (Claude's discretion on exact wording) should follow the KRITISCH convention already established in the codebase. Example:

```python
exclusion_hint = ""
if selected_stops:
    exclusion_hint = (
        "KRITISCH — Duplikat-Vermeidung: Schlage KEINEN der folgenden bereits "
        "ausgewählten Stopps erneut vor: "
        + ", ".join(s["region"] for s in capped_stops)
        + ". Diese Orte sind bereits Teil der Route.\n"
    )
```

### History Capping Pattern (D-09)

Apply before building `stops_str`. Claude's discretion on threshold — suggesting 8/5 as per discussion:

```python
MAX_HISTORY_FULL = 8   # if len(selected_stops) <= this, show all
TAIL_COUNT = 5         # else show last N + summary prefix

capped_stops = selected_stops
history_prefix = ""
if len(selected_stops) > MAX_HISTORY_FULL:
    capped_stops = selected_stops[-TAIL_COUNT:]
    history_prefix = f"{len(selected_stops)} bisherige Stopps, letzte {TAIL_COUNT}: "
```

### Post-Processing Dedup Pattern (D-03, D-04, D-05)

Inside `_find_and_stream_options._enrich_one()`, after enrichment succeeds. The existing confirm-route dedup pattern (line 1740) uses `{s.get("region", "").lower()}` — replicate exactly:

```python
# In _enrich_one(), after Google enrichment completes, before proximity check:
opt_region = opt.get("region", "").lower()
already_selected = {s.get("region", "").lower() for s in selected_stops}
if opt_region in already_selected:
    await debug_logger.log(
        LogLevel.DEBUG,
        f"  Verworfen (Duplikat bereits ausgewählt: {opt.get('region')})",
        job_id=job_id, agent="StopOptionsFinder",
    )
    return None
```

**Critical placement note:** `_enrich_one` is an inner async function defined inside `_run_one_pass` inside `_find_and_stream_options`. It receives `opt` (the individual option dict) but does not directly receive `selected_stops`. `selected_stops` is in the outer function's closure scope and is accessible. Verify this by checking line 835: `async def _enrich_one(i: int, opt: dict) -> Optional[dict]:` — the closure captures `selected_stops` from `_find_and_stream_options`'s parameter list (line 723).

### architect_context Wiring Gap (Critical Finding)

Phase 13 wired `architect_context=architect_plan` only in `_start_leg_route_building` (line 354). The `select_stop` endpoint has **two** `_find_and_stream_options` call sites that do NOT pass `architect_context`:

1. **Line 1356-1370** — segment transition path (`route_status["must_complete"] and not is_last_segment`)
2. **Line 1465-1478** — normal continue-building path (`else` branch)

And `recompute_options` (line 1543-1557) also does not pass it.

All three need:
```python
architect_context=job.get("architect_plan"),
```

This is already stored in job state from Phase 13 (`job["architect_plan"]`). The fix is purely additive — no state changes needed.

### Night Distribution Injection (D-06, D-07)

The architect plan's `regions` list contains `{"name": "...", "recommended_nights": N, "max_drive_hours": X}`. To pre-fill `recommended_nights` in options, the prompt must tell Claude which region the current stop corresponds to.

**Fuzzy match strategy (Claude's discretion):** The architect plan uses broad region names (e.g., "Schwarzwald", "Elsass") while StopOptionsFinder produces city names (e.g., "Freiburg", "Colmar"). A simple index-based approach is more reliable than string matching:

- Track a `current_region_index` in job state or derive it from `stop_counter` vs `estimated_total_stops`
- Alternatively, use the `stop_number` position relative to `estimated_total_stops` to select the nth architect region
- Simplest approach: use the existing `architect_block` in `_build_prompt()` and add a specific nights prompt for the current region. Example:

```python
# Enhanced architect_block (D-07): add nights suggestion for current stop
if architect_context:
    regions = architect_context.get("regions", [])
    if regions:
        # Position-based: which region are we in?
        # stop_number / estimated_total_stops gives fractional position
        region_idx = min(int(stop_number / max(1, estimated_stops_hint) * len(regions)), len(regions) - 1)
        current_region = regions[region_idx]
        architect_block += (
            f"FÜR DIESEN STOP: Empfehle {current_region['recommended_nights']} Nächte "
            f"(basierend auf Potential der Region {current_region['name']}).\n"
        )
```

Note: `_build_prompt()` currently does not receive `stop_number`/`estimated_total_stops` as a direct correlator for region selection. The simplest safe approach is to pass the hint through or use a fallback (first unmatched region). This is a discretion area — the planner should document the chosen strategy.

### Night Budget UI (D-08)

`_updateRouteStatus(meta)` in `route-builder.js` (line 321-347) builds the subtitle text. `meta.days_remaining` is already available. The "Nächte verbleibend" display needs:

1. Backend: expose `nights_remaining` in the `meta` response (or compute client-side from `days_remaining`)
2. Frontend: append to subtitle or add a dedicated badge

Current subtitle format: `"Etappe 1/2 (Transit) · Stop #3 · → Paris · 5 Tage verbleibend"`

Since `days_remaining` already exists and nights ≈ days (with minor drive-day adjustments), the simplest approach is to compute client-side: `nights_remaining = meta.days_remaining - 1` or expose a dedicated `nights_remaining` field from the backend. The backend `_calc_route_status()` returns `days_remaining` — a thin `nights_remaining` wrapper is sufficient.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Dedup logic | Custom Levenshtein/fuzzy matching | Case-insensitive exact `region` match (D-03 locked) |
| History management | External cache or DB lookup | In-memory capped slice of `selected_stops` list |
| Region matching for nights | ML/embedding similarity | Index-based position in architect_plan regions list |

---

## Common Pitfalls

### Pitfall 1: Dedup check placement in streaming vs batch path

**What goes wrong:** The dedup check added to `_enrich_one` affects the streaming path. The retry logic (lines 999-1020) merges retry options into `enriched_options` using its own `existing_regions` set. If the dedup check only fires in `_enrich_one`, a duplicate that slips through a retry pass could bypass it.

**Why it happens:** The retry merge on line 1014 builds its own `existing_regions = {o.get("region") for o in enriched_options}` — this only deduplicates against the current enriched batch, not against `selected_stops`.

**How to avoid:** The dedup check in `_enrich_one` handles `selected_stops` dedup. The retry merge's `existing_regions` handles intra-batch dedup. Both checks are needed and cover different cases.

**Warning signs:** A stop appears twice in enriched_options — means the retry merge's existing_regions check fired but not the selected_stops check.

### Pitfall 2: `selected_stops` reference in `_enrich_one` closure

**What goes wrong:** `_enrich_one` is a nested async function inside `_run_one_pass` inside `_find_and_stream_options`. It references `selected_stops` from the outer scope. In Python, closures capture variables by reference — this is fine for a read-only list. But if `selected_stops` were mutated between calls to `_enrich_one`, results would be non-deterministic.

**Why it happens:** `asyncio.gather` runs `_enrich_one` concurrently for all options. `selected_stops` is not mutated during this phase (stops are only appended in `select_stop` endpoint, not inside `_find_and_stream_options`), so this is safe.

**How to avoid:** No change needed — the existing parallel gather pattern is safe for read-only closure access.

### Pitfall 3: architect_context not wired in all call sites

**What goes wrong:** The `recommended_nights` enhancement only fires when `architect_context` is not None. If the 3 call sites in `select_stop`/`recompute_options` are not updated, the feature silently does nothing after the first stop.

**Why it happens:** Phase 13 only wired `_start_leg_route_building`. The other call sites were not updated per STATE.md decision: "Other `_find_and_stream_options` call sites receive `architect_context=None` by default."

**How to avoid:** Phase 14 must explicitly wire all 3 remaining call sites (lines 1356-1370, 1465-1478, 1543-1557) with `architect_context=job.get("architect_plan")`. This is the core wiring work of D-07.

### Pitfall 4: Prompt placement of exclusion rule affects token timing

**What goes wrong:** If the KRITISCH exclusion rule is placed at the end of the user prompt (after the JSON template), Claude may already have mentally committed to options by the time it encounters the constraint.

**Why it happens:** LLMs process prompts left-to-right and weight early context more heavily.

**How to avoid:** Place the exclusion rule early in the user prompt, immediately after `stops_str` (which lists the stops), not at the end. The natural location is right before the `option_block`.

### Pitfall 5: History cap removes start_location from context

**What goes wrong:** When capping to the last 5 stops, the first stop provides geographic anchor context. Losing it may cause the model to suggest geographically invalid options on very long trips.

**Why it happens:** Naive tail-slicing removes early route context.

**How to avoid:** `prev_stop` (the last selected stop's region) is already set as "Letzter Stop (Abfahrtspunkt)" in the prompt independently of `stops_str`. The exclusion rule only needs the region names, not the full stop metadata. A capped summary like "12 bisherige Stopps, letzte 5: ..." gives enough context.

---

## Code Examples

### Verified: Existing silent-reject pattern in `_enrich_one`
```python
# Source: backend/main.py lines 869-878 (proximity check)
if origin_coords and min_km_from_origin > 0:
    d_origin = _haversine_km(origin_coords, coords)
    if d_origin < min_km_from_origin:
        await debug_logger.log(
            LogLevel.DEBUG,
            f"  Verworfen (zu nahe am Startpunkt {origin_location}: {d_origin:.0f} km < {min_km_from_origin:.0f} km): {place}",
            job_id=job_id, agent="StopOptionsFinder",
        )
        return None
```

### Verified: Existing confirm-route dedup pattern
```python
# Source: backend/main.py lines 1739-1756
existing_regions = {s.get("region", "").lower() for s in selected_stops}
for vp in request.via_points:
    if vp.location.lower() not in existing_regions:
        # ... append
        existing_regions.add(vp.location.lower())
```

### Verified: `_updateRouteStatus` subtitle building
```python
// Source: frontend/js/route-builder.js lines 321-339
const parts = [legInfo, `Stop #${stopNum}`, segInfo, daysRem ? `${daysRem} Tage verbleibend` : ''].filter(Boolean);
subtitle.textContent = parts.join(' · ');
```

### Verified: `architect_block` current implementation
```python
# Source: backend/agents/stop_options_finder.py lines 118-132
architect_block = ""
if architect_context:
    regions = architect_context.get("regions", [])
    if regions:
        region_lines = []
        for r in regions:
            nights_hint = f"{r['recommended_nights']}N"
            drive_hint = f", ~{r['max_drive_hours']}h" if r.get('max_drive_hours') else ""
            region_lines.append(f"{r['name']} ({nights_hint}{drive_hint})")
        summary = " → ".join(region_lines)
        architect_block = (
            f"\nARCHITECT-EMPFEHLUNG: {summary}\n"
            f"Die Nächteangaben sind Empfehlungen basierend auf dem Potential der Orte — du kannst davon abweichen.\n"
        )
```

---

## State of the Art

| Old Approach | Current Approach | Phase |
|--------------|-----------------|-------|
| `architect_context=None` in select_stop | `architect_context=job.get("architect_plan")` | Phase 14 |
| No dedup in `_find_and_stream_options` | Silent drop on `region in selected_regions` set | Phase 14 |
| Full history in prompt regardless of length | Capped to last 5 + count summary when >8 | Phase 14 |
| Generic nights range in prompt | `recommended_nights` per-stop default from architect | Phase 14 |

---

## Open Questions

1. **Region index for `recommended_nights` injection**
   - What we know: architect plan has N regions; current stop is stop #K of ~M total
   - What's unclear: the safest mapping between stop_number and architect region index
   - Recommendation: Use `min(int(stop_number / total_estimated * len(regions)), len(regions) - 1)` — gracefully degrades to last region if estimates are off. Alternatively, scan regions in order and use the first one not yet "consumed" based on nights used vs nights recommended.

2. **`nights_remaining` — backend field vs client-side compute**
   - What we know: `days_remaining` is already in meta; nights are roughly days minus drive days
   - What's unclear: exact formula (days_remaining includes the final destination night?)
   - Recommendation: Expose a dedicated `nights_remaining = max(0, days_remaining - 1)` in the meta response, keeping the semantics explicit.

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified — pure Python/JS code changes only)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | none (no pytest.ini detected) |
| Quick run command | `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RTE-03 | `_build_prompt()` includes KRITISCH exclusion rule when stops are selected | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_stop_options_exclusion_rule" -x` | ❌ Wave 0 |
| RTE-03 | History capping: >8 stops → last 5 + count summary | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_stop_history_cap" -x` | ❌ Wave 0 |
| RTE-04 | `_find_and_stream_options` silently drops options whose `region` matches a selected stop | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_postprocessing_dedup" -x` | ❌ Wave 0 |
| RTE-04 | Dedup is case-insensitive | unit | `cd backend && python3 -m pytest tests/test_agents_mock.py -k "test_dedup_case_insensitive" -x` | ❌ Wave 0 |
| D-08 | `nights_remaining` appears in meta response from select_stop | unit | `cd backend && python3 -m pytest tests/test_endpoints.py -k "nights_remaining" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_agents_mock.py` — add test class or functions for StopOptionsFinder dedup + history cap
- [ ] `tests/test_endpoints.py` — add `nights_remaining` field assertion in existing `/api/select-stop` tests if present

*(The test infrastructure (conftest.py, mock patterns) already exists — only new test functions are needed)*

---

## Project Constraints (from CLAUDE.md)

Directives applicable to this phase:

- All user-facing text in German (exclusion rule prompt text must be German)
- Agents always return valid JSON — no markdown wrappers
- All Claude calls go through `call_with_retry()` (no change needed — no new agent)
- Agent JSON parsing via `parse_agent_json()` (no change needed)
- Log every API call with `debug_logger.log(LogLevel.API, ...)` (no change needed — existing logging)
- KRITISCH rules are the established convention for hard constraints in StopOptionsFinder prompts
- `esc()` for all user-content interpolation into HTML (frontend night badge must use esc() if dynamic)
- File-based logging required: new log calls use `agent="StopOptionsFinder"` (existing component map entry)
- No new dependencies — stdlib only
- TEST_MODE=true → all agents use claude-haiku-4-5 (no model changes in this phase)

---

## Sources

### Primary (HIGH confidence)
- `backend/agents/stop_options_finder.py` — full audit of `_build_prompt()`, `find_options_streaming()`, existing KRITISCH patterns
- `backend/agents/architect_pre_plan.py` — confirmed `regions[].recommended_nights` structure
- `backend/main.py` lines 719-1020 — `_find_and_stream_options` full code audit, `_enrich_one` closure scope
- `backend/main.py` lines 1255-1502 — `select_stop` endpoint all three `_find_and_stream_options` call sites
- `backend/main.py` lines 1509-1580 — `recompute_options` endpoint
- `backend/main.py` lines 1737-1776 — existing confirm-route dedup pattern (reference implementation)
- `frontend/js/route-builder.js` lines 1-450 — `_updateRouteStatus`, `_buildOptionCardHTML`, `renderOptions`

### Secondary (MEDIUM confidence)
- `.planning/phases/14-stop-history-awareness-night-distribution/14-CONTEXT.md` — all decisions
- `.planning/phases/13-architect-pre-plan-for-interactive-flow/13-CONTEXT.md` — Phase 13 wiring context (D-05, D-10, D-11)
- `.planning/STATE.md` — "Other call sites receive architect_context=None by default" decision recorded

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all changes are internal to existing files with verified patterns
- Architecture: HIGH — dedup pattern copied verbatim from confirm-route dedup; prompt placement follows established KRITISCH convention
- Pitfalls: HIGH — all identified from direct code audit, not speculation

**Research date:** 2026-03-29
**Valid until:** 2026-06-01 (stable codebase, no fast-moving dependencies)
