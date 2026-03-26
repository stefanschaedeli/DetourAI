# Phase 6: Wiring Fixes - Research

**Researched:** 2026-03-26
**Domain:** Cross-phase integration fixes (frontend SSE, backend data wiring, agent prompts)
**Confidence:** HIGH

## Summary

Phase 6 closes five audit gaps from the v1.0 milestone audit. All gaps are well-scoped wiring issues where one end of the integration exists but the other is missing or incomplete. The fixes span four distinct areas: (1) share_token not returned by GET endpoint on reload, (2) replace-stop hints stored but not forwarded to the agent, (3) two SSE events emitted by backend but not registered in the frontend event list, and (4) stop tags field defined in the model but never populated by agents.

Every fix has been traced to specific lines of code. The share_token fix requires modifying one SQL query in `travel_db.py`. The hints fix is already wired in the `api_replace_stop` search-mode path (line 2353) but the manual-mode path stores hints without forwarding them — however, the manual path geocodes directly and does not call the agent, so no agent wiring is needed there. The SSE fix requires adding two event names to the `events` array in `api.js` and adding handler functions. The tags fix requires updating agent prompts and the `StopOption` model to include a `tags` field.

**Primary recommendation:** Fix in order of functional severity: share_token persistence > SSE event registration > tags population > hints verification. All changes are surgical (< 50 lines each).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Share toggle fix via API refetch — `apiGetTravel()` already returns share_token if the SQL query includes it. Fix `_sync_get` to SELECT share_token.
- D-02: Add text input in replace-stop dialog with German placeholder `z.B. mehr Strand, weniger Fahrzeit`.
- D-03: Hints field is optional — no friction added.
- D-04: Register `style_mismatch_warning` and `ferry_detected` in `openSSE()` events array in `api.js`. Add handlers in `progress.js`.
- D-05: Both events display as toast notifications — brief, auto-dismissing, non-blocking.
- D-06: `style_mismatch_warning` uses warning style (amber/yellow).
- D-07: `ferry_detected` uses informational style (blue/neutral).
- D-08: Verify ferry cost wired into budget display.
- D-09: Both StopOptionsFinder and ActivitiesAgent contribute tags.
- D-10: Tags in German. Examples: "Strand", "Kultur", "Wandern", "Kueste", "Insel", "Natur", "Berge".
- D-11: Maximum 3-4 tags per stop. Agent prompts request this limit explicitly.
- D-12: Tags field exists on TravelStop model. Frontend renders with `stop-tag-pill` CSS class. Only agent prompts and response parsing need changes.

### Claude's Discretion
- Toast notification styling and positioning (top vs bottom, auto-dismiss duration)
- Exact tag vocabulary — Claude can pick appropriate German tags from context
- How to merge/deduplicate tags when both agents contribute (simple union with dedup is fine)

### Deferred Ideas (OUT OF SCOPE)
- Multi-language support for the entire app
- Preset hint chips for replace-stop (quick-select buttons)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CTL-04 | Replace stop with guided hints flow | Hints input already in UI (guide.js:2763). Backend search-mode already forwards hints (main.py:2353). Manual-mode does not use agent so no wiring needed. Audit gap was about `_find_and_stream_options` call — verified this IS wired in search-mode. |
| SHR-01 | Generate shareable link (persistence on reload) | `_sync_get` selects only `plan_json` (travel_db.py:115). Must also SELECT `share_token` and inject into returned dict. Frontend already reads `plan.share_token` in `showTravelGuide()` (guide.js:44). |
| AIQ-03 | Travel style enforcement (SSE warning display) | `style_mismatch_warning` emitted by route_architect.py:156. Handler exists in route-builder.js:108. Missing from `events` array in api.js:374-384, so `addEventListener` never called. |
| GEO-01 | Ferry crossing detection (SSE notification) | `ferry_detected` emitted by route_architect.py:169. No handler exists yet in frontend. Must add to events array AND create handler. |
| UIR-03 | Stop cards with travel style tags | `TravelStop.tags` field exists (travel_response.py:96). Frontend renders tags (guide.js:1084-1087). `StopOption` model lacks `tags` field. Agent prompts don't request tags in JSON schema. |
</phase_requirements>

## Architecture Patterns

### Fix 1: share_token persistence (SHR-01)

**Current flow (broken):**
```
GET /api/travels/{id} → api_get_travel() → get_travel() → _sync_get()
  → SELECT plan_json FROM travels WHERE id=? AND user_id=?
  → Returns JSON without share_token
  → Frontend: plan.share_token is undefined → toggle shows unchecked
```

**Fixed flow:**
```
_sync_get() → SELECT plan_json, share_token, id FROM travels WHERE id=? AND user_id=?
  → plan = json.loads(row["plan_json"])
  → plan["_saved_travel_id"] = row["id"]
  → plan["share_token"] = row["share_token"]  # None if not shared
  → Frontend: plan.share_token has correct value → toggle renders correctly
```

**Pattern reference:** `_sync_get_by_share_token` (travel_db.py:221-232) already does this correctly — inject `_saved_travel_id` into the returned plan dict. Mirror this pattern in `_sync_get`.

**Key detail:** The `_saved_travel_id` is currently NOT injected by `_sync_get` either, but the frontend sets it via `openSavedTravel()` in travels.js. Still, adding it in `_sync_get` is defensive and consistent with `_sync_get_by_share_token`.

### Fix 2: SSE event registration (AIQ-03, GEO-01)

**Current state:**
- `api.js:374-384` — events array has 20 event types but missing `style_mismatch_warning` and `ferry_detected`
- `route-builder.js:25` — handler `_onStyleMismatchWarning` is registered in `openRouteSSE()` which calls `openSSE()`, but since the event name is not in the events array, the `addEventListener` is never called
- No `ferry_detected` handler exists anywhere in the frontend

**Fix approach:**
1. Add `'style_mismatch_warning'` and `'ferry_detected'` to the `events` array in `api.js`
2. The route-builder.js handler for `style_mismatch_warning` already works (renders a plausibility banner) — it will start firing once the event is registered
3. Create `ferry_detected` handler — either in route-builder.js (alongside style_mismatch) or progress.js
4. Both should also fire toast notifications per D-05/D-06/D-07

**SSE event data shapes (from backend):**
```python
# style_mismatch_warning (route_architect.py:156-159)
{
    "warning": str,           # Warning text
    "suggestions": [str],     # List of suggestion strings
    "original_styles": [str], # User's travel styles
}

# ferry_detected (route_architect.py:169-171)
{
    "crossings": list,        # Ferry crossing details from route architect
    "island_group": str,      # e.g. "cyclades", "corsica"
}
```

### Fix 3: Stop tags population (UIR-03)

**Current state:**
- `TravelStop.tags: List[str] = []` exists (travel_response.py:96)
- `StopOption` model has NO `tags` field (stop_option.py:5-31)
- Agent prompt JSON schema does not include `tags`
- Frontend guide.js:1084-1087 renders `stop-tag-pill` but array is always empty

**Fix approach — two injection points:**

1. **StopOptionsFinderAgent** (initial tags during route building):
   - Add `tags` field to `StopOption` model: `tags: List[str] = []`
   - Add `"tags": ["Strand", "Kultur"]` to the JSON example in the prompt (stop_options_finder.py:242-244)
   - Add instruction: "tags: 3-4 deutsche Schlagworte die den Charakter des Stopps beschreiben"
   - Tags flow: agent response → `StopOption` parsing → stored in selected_stops → carried into `TravelStop`

2. **ActivitiesAgent** (enrichment during research phase):
   - Add `"tags": ["Wandern", "Natur"]` to the JSON response schema
   - After parsing response, merge tags into the stop's existing tags
   - Dedup with `list(set(existing_tags + new_tags))[:4]` to enforce max 4

**Tag transfer chain:**
```
StopOptionsFinderAgent → StopOption.tags → selected_stops[i]["tags"]
  → Orchestrator builds TravelStop → TravelStop.tags carries initial tags
  → ActivitiesAgent → enriches with activity-based tags
  → Final TravelStop.tags = deduplicated union, max 4
```

**Where tags transfer from StopOption to TravelStop:** This happens in the orchestrator when building the stops list. Need to verify the orchestrator copies tags from the selected stop dict into the TravelStop construction.

### Fix 4: Replace-stop hints verification (CTL-04)

**Audit finding:** "hints field stored but not forwarded to StopOptionsFinderAgent"

**Investigation result:** The audit was partially wrong. In the `api_replace_stop` endpoint:
- **Search mode** (main.py:2340-2353): `extra_instructions=body.hints or ""` IS passed to `_find_and_stream_options`. This is already wired correctly.
- **Manual mode** (main.py:2283-2312): User enters a specific location — no agent call is made, so hints are not applicable.

**Remaining gap:** The UI hint input (guide.js:2763) is only in the "manual" tab. For search mode (the "Neue Suche" tab), hints are read from the same input field (guide.js:2847). The input field needs to also be visible/accessible in the search tab OR the search tab needs its own hints input.

Looking at the code: `_doSearchReplace` reads hints from `replace-stop-hints` (guide.js:2847), which is in the manual tab. When user switches to search tab, the manual tab is hidden (`display:none`). The hints input is still accessible via `getElementById` even when hidden, so technically the value can be read. But UX-wise, users on the search tab won't see the hints field.

**Fix needed:** Add a hints input to the search tab as well, OR move the hints input to a shared section above the tabs.

### Toast Notification Pattern

**Existing pattern:** Settings toast (settings.js:352-356, styles.css:3745-3764) uses fixed position bottom-right, auto-dismiss after 1.5s. This is a good base pattern.

**New toasts need:**
- Warning toast (amber): for `style_mismatch_warning`
- Info toast (blue): for `ferry_detected`
- Auto-dismiss: 5-8 seconds (longer than settings toast since these contain important info)
- Stacking: if both fire, they should stack vertically

**Implementation recommendation:** Create a reusable `showToast(message, type)` function rather than duplicating the settings pattern. Types: `'info'` (blue), `'warning'` (amber), `'success'` (green/accent). CSS classes: `app-toast`, `app-toast-info`, `app-toast-warning`.

### Anti-Patterns to Avoid
- **Modifying plan_json in DB:** Never alter the stored JSON to include share_token — it belongs as a separate column (which it already is)
- **Inline CSS for toasts:** Use CSS classes consistent with DESIGN_GUIDELINE.md
- **Tags in English:** All user-facing tags must be in German per project convention

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Toast notifications | Complex notification queue | Simple DOM append + setTimeout remove | Only 2 event types, no queue needed |
| Tag deduplication | Complex merge logic | `list(set(a + b))[:4]` | Simple string list, no complex merging |

## Common Pitfalls

### Pitfall 1: StopOption tags not carrying through to TravelStop
**What goes wrong:** Tags added to StopOption model but lost when orchestrator builds TravelStop from selected_stops dict.
**Why it happens:** The orchestrator constructs TravelStop from the stop dict — if `tags` key isn't in the dict, it defaults to `[]`.
**How to avoid:** Verify the data flow: agent response dict → stored in `selected_stops` → orchestrator reads `tags` key when building TravelStop. The key must survive the dict serialization through Redis job state.
**Warning signs:** Tags appear in agent logs but not in the final travel plan.

### Pitfall 2: EventSource handler not firing despite event in array
**What goes wrong:** Event added to `events` array but handler not passed in the `handlers` object for that specific SSE connection.
**Why it happens:** `openSSE()` only calls `addEventListener` for events that have a matching handler in the `handlers` object. Route-builder.js already passes `style_mismatch_warning` handler. But `connectSSE()` in progress.js does not — if the user is on the progress page, these events won't be handled.
**How to avoid:** Add handlers to BOTH `openRouteSSE()` in route-builder.js AND `connectSSE()` in progress.js, since route building can trigger these events during both interactive route building AND the orchestrated planning phase.

### Pitfall 3: Hints input not accessible in search tab
**What goes wrong:** User switches to "Neue Suche" tab, can't enter hints because the input is in the hidden "manual" tab.
**How to avoid:** Either move hints input above the tabs (shared section) or duplicate it in the search tab.

### Pitfall 4: share_token column might be NULL in SQLite
**What goes wrong:** `row["share_token"]` returns `None` for travels that were never shared — this is correct and expected.
**How to avoid:** Frontend already handles `null` correctly: `plan.share_token || null` in guide.js:44. Just ensure the backend injects `None` (not omitting the key).

## Code Examples

### share_token fix in _sync_get (travel_db.py)
```python
# Current (broken):
def _sync_get(travel_id: int, user_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT plan_json FROM travels WHERE id=? AND user_id=?",
            (travel_id, user_id),
        ).fetchone()
    return json.loads(row["plan_json"]) if row else None

# Fixed:
def _sync_get(travel_id: int, user_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, plan_json, share_token FROM travels WHERE id=? AND user_id=?",
            (travel_id, user_id),
        ).fetchone()
    if row is None:
        return None
    plan = json.loads(row["plan_json"])
    plan["_saved_travel_id"] = row["id"]
    plan["share_token"] = row["share_token"]
    return plan
```

### SSE events array fix (api.js)
```javascript
// Add to events array at line 374-384:
const events = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'region_plan_ready', 'region_updated', 'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress', 'remove_stop_complete',
    'add_stop_progress', 'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'style_mismatch_warning', 'ferry_detected',  // Phase 6 addition
];
```

### Toast notification function (new)
```javascript
function showToast(message, type) {
  // type: 'info' | 'warning'
  const toast = document.createElement('div');
  toast.className = `app-toast app-toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 6000);
}
```

### StopOption tags field addition (stop_option.py)
```python
class StopOption(BaseModel):
    # ... existing fields ...
    travel_style_match: bool = True
    is_ferry_required: bool = False
    tags: List[str] = []  # Phase 6: German descriptive tags
```

### Agent prompt tags instruction (stop_options_finder.py)
```
# Add to JSON example, after "matches_travel_style":
"tags": ["Strand", "Kultur"]

# Add to field descriptions:
- tags: 3-4 kurze deutsche Schlagworte die den Charakter und die Staerken des Stopps beschreiben
  (z.B. "Strand", "Kultur", "Wandern", "Kueste", "Insel", "Natur", "Berge", "Altstadt", "Weinregion", "Familienfreundlich")
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | None (convention-based) |
| Quick run command | `cd backend && python3 -m pytest tests/test_travel_db.py -x -q` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SHR-01 | _sync_get returns share_token | unit | `pytest tests/test_travel_db.py::test_get_includes_share_token -x` | Wave 0 |
| CTL-04 | Hints input accessible in search tab | manual-only | Browser verification | N/A |
| AIQ-03 | style_mismatch_warning in events array | manual-only | Browser verification (SSE) | N/A |
| GEO-01 | ferry_detected in events array | manual-only | Browser verification (SSE) | N/A |
| UIR-03 | StopOption model accepts tags field | unit | `pytest tests/test_models.py -x -k tags` | Wave 0 |
| UIR-03 | Agent prompt requests tags | unit | `pytest tests/test_agents_mock.py -x -k tags` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/ -x -q`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_travel_db.py::test_get_includes_share_token` -- covers SHR-01
- [ ] `tests/test_models.py` -- add test for StopOption with tags field (UIR-03)
- [ ] `tests/test_agents_mock.py` -- verify StopOptionsFinder prompt includes "tags" (UIR-03)

## Open Questions

1. **Tags transfer through orchestrator**
   - What we know: StopOption will have tags, TravelStop has tags field, frontend renders tags
   - What's unclear: Whether orchestrator.py copies `tags` from the selected_stops dict when constructing TravelStop objects for the final plan
   - Recommendation: Trace the orchestrator code during implementation; if tags are dropped, add explicit copy

2. **Ferry cost budget display verification (D-08)**
   - What we know: Ferry cost formula exists (CHF 50 base + CHF 0.5/km), ferry_cost_chf field on TravelStop
   - What's unclear: Whether the cost summary/budget display includes ferry costs
   - Recommendation: Verify during implementation; this is a display-only check

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all referenced files in the working repository
- v1.0 Milestone Audit report (.planning/v1.0-MILESTONE-AUDIT.md)
- Phase 6 CONTEXT.md with locked decisions

### Confidence Assessment
All findings are HIGH confidence — derived from direct code reading of the actual codebase, not external documentation or training data.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all fixes use existing codebase patterns
- Architecture: HIGH - all integration points verified by reading actual source code
- Pitfalls: HIGH - derived from tracing actual data flows through the codebase

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable codebase, no external dependencies changing)
