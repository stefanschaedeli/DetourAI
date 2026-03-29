# Phase 12: Context Infrastructure + Wishes Forwarding - Research

**Researched:** 2026-03-29
**Domain:** Agent prompt engineering + vanilla JS form extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Three distinct fields maintained: `travel_description` (free-text trip vision), `preferred_activities` (soft preference tags), `mandatory_activities` (must-do items with optional location)
- **D-02:** `preferred_activities` uses structured tag input (same pattern as mandatory activities), not free text
- **D-03:** All wishes fields go in Step 2 alongside travel styles and travelers — natural flow: where -> how -> what -> budget -> confirm
- **D-04:** `preferred_activities` uses same tag-chip input pattern as existing `S.mandatoryTags` for consistent UX
- **D-05:** `travel_description` textarea gets a German placeholder with example: "Beschreibe deine Traumreise... z.B. Romantischer Roadtrip durch die Provence mit Weinproben und kleinen Dorfern"
- **D-06:** Prompts are tailored per agent role — each agent gets the fields relevant to its task
- **D-07:** All agents get all three fields (`travel_description`, `preferred_activities`, `mandatory_activities`) — maximum context, agents ignore what they don't need
- **D-08:** Follow ActivitiesAgent's existing pattern: conditionally include fields only when non-empty, as labeled sections in the prompt

### Per-Agent Field Assignment

| Agent | travel_description | preferred_activities | mandatory_activities | Status |
|-------|:--:|:--:|:--:|---|
| RouteArchitectAgent | already done | ADD | already done | Partial |
| StopOptionsFinderAgent | ADD | ADD | ADD | Needs all |
| RegionPlannerAgent | ADD | ADD | ADD | Needs all |
| AccommodationResearcherAgent | ADD | ADD | ADD | Needs all |
| ActivitiesAgent | already done | already done | already done | Complete |
| RestaurantsAgent | ADD | ADD | ADD | Needs all |
| DayPlannerAgent | ADD | ADD | ADD | Needs all |
| TravelGuideAgent | ADD | ADD | ADD | Needs all |
| TripAnalysisAgent | ADD | ADD | already done | Partial |

### Claude's Discretion

- Exact German labels and placeholder wording for the new form fields
- Ordering of wishes fields within Step 2 (relative to styles and travelers)
- Exact prompt phrasing per agent (follow German prompt convention)

### Deferred Ideas (OUT OF SCOPE)

- "RouteArchitect ignores daily drive limits and suggests ferries/islands" — Phase 13 scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CTX-01 | User kann globale Aktivitätswünsche als Freitext im Trip-Formular eingeben | Frontend: `preferred_activities` tag input in Step 2 (index.html + form.js + state.js). `travel_description` textarea already exists in Step 2 but needs better placeholder per D-05. |
| CTX-02 | `travel_description` und `preferred_activities` werden an alle 9 Agents weitergeleitet | 8 agent prompt files need conditional blocks added; `buildPayload()` must populate `preferred_activities` from `S.preferredTags`; orchestrator already passes full TravelRequest — no orchestrator changes needed. |
| CTX-03 | `mandatory_activities` werden an StopOptionsFinder und ActivitiesAgent weitergeleitet | ActivitiesAgent already has it. StopOptionsFinderAgent `_build_prompt()` method needs mandatory_activities block added. |
</phase_requirements>

---

## Summary

Phase 12 is a mechanical, well-scoped change across two layers: (1) frontend form UI, (2) agent prompt strings. The data model (`TravelRequest`) already has all three fields with proper validation. The orchestrator already passes the full `TravelRequest` to all agents — no plumbing changes are needed anywhere in the pipeline.

The canonical reference implementation is `ActivitiesAgent` (lines 183–185 of `activities_agent.py`): three conditional f-string lines appended to the prompt when the field is non-empty. Every other agent needs the same three lines inserted in the appropriate location within their prompt string. The conditional pattern ensures zero behavioral change when users leave fields empty.

On the frontend, the tag-chip input pattern (`S.mandatoryTags` / `mandatory-tag-input` / `mandatory-tags` / `renderTags()` / `addTagFromInput()`) must be duplicated for `preferred_activities`, targeting new IDs. `buildPayload()` already has a placeholder `preferred_activities: []` hardcoded — it just needs to be wired to `S.preferredTags`.

**Primary recommendation:** Copy the ActivitiesAgent pattern verbatim to all 7 agent files that need it; mirror the mandatoryTags JS pattern for preferredTags; update `buildPayload()` and localStorage cache.

---

## Standard Stack

No new libraries or packages are needed. This phase is entirely within the existing codebase.

| Component | Location | Current State | Change Needed |
|-----------|----------|--------------|----------------|
| TravelRequest Pydantic model | `backend/models/travel_request.py` | All 3 fields defined, validated | None |
| ActivitiesAgent (reference) | `backend/agents/activities_agent.py:183-185` | All 3 fields in prompt | None — read-only reference |
| 8 agent prompt files | Various `backend/agents/` files | Missing 1–3 fields each | Add conditional blocks |
| Frontend state | `frontend/js/state.js` | `S.mandatoryTags: []` exists; `S.preferredTags` missing | Add `preferredTags: []` to S |
| Frontend form | `frontend/js/form.js` | `preferred_activities: []` hardcoded in buildPayload | Wire to `S.preferredTags`; add tag-input functions |
| Frontend HTML | `frontend/index.html` | `preferred_activities` UI absent from Step 2 | Add tag-chip input block |
| Frontend localStorage | `form.js:saveFormToCache()` | mandatoryTags persisted; preferredTags not | Add preferredTags to cache/restore |

---

## Architecture Patterns

### Pattern 1: Conditional Wishes Block in Agent Prompts

This is the **canonical pattern** from `ActivitiesAgent` — copy exactly.

```python
# Source: backend/agents/activities_agent.py lines 183-185
desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
mandatory_line = f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""
```

These three lines are declared before the prompt f-string and then interpolated inline:

```python
# In the prompt f-string, append at a natural break after core context lines:
prompt = f"""...(existing content)...
{mandatory_line}{pref_line}{desc_line}
...(rules/schema)..."""
```

**Insertion point per agent:** After the core request parameters (travelers, styles, dates, budget) and before rules or JSON schema. The ActivitiesAgent inserts them after `Aktivitätenbudget:...` — each agent should follow the same "parameters first, then enrichment context, then rules" order.

### Pattern 2: RouteArchitectAgent — preferred_activities Only

RouteArchitect already has `travel_description` (line 122) and `mandatory_activities` (lines 47–50 / 126). It only needs `preferred_activities` added.

Existing mandatory_activities block in route_architect.py:
```python
# lines 47-50
mandatory_str = ""
if req.mandatory_activities:
    acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
    mandatory_str = f"Pflichtaktivitäten: {', '.join(acts)}\n"
```

Add analogously:
```python
pref_str = f"Bevorzugte Aktivitäten: {', '.join(req.preferred_activities)}\n" if req.preferred_activities else ""
```

Then insert `{pref_str}` in the prompt after `{mandatory_str}`.

### Pattern 3: TripAnalysisAgent — travel_description + preferred_activities

TripAnalysisAgent already has `mandatory_activities` (line 45 and 57). Needs `travel_description` and `preferred_activities` added to its "Benutzeranforderungen" block.

Current prompt block (lines 47–60):
```python
prompt = f"""Analysiere diesen Reiseplan...
## Benutzeranforderungen
- Startort: ...
- Reisestile: {travel_styles_str}
- Unterkunftswünsche: {prefs_str}
- Pflichtaktivitäten: {mandatory_acts}
```

Add two lines after the existing ones:
```python
travel_desc_line = f"- Reisebeschreibung: {req.travel_description}" if req.travel_description else ""
pref_acts_line   = f"- Bevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
```

### Pattern 4: RegionPlannerAgent — Inject via description

RegionPlannerAgent.plan() is called with a `description: str` argument (the explore leg description or similar). The wishes context belongs in the `_leg_context()` method or appended to the description passed to `plan()`. The cleanest insertion is in `_leg_context()` — append wishes lines after `Reisestile:`.

```python
def _leg_context(self, leg_index: int) -> str:
    ...
    lines.append(f"Reisestile: {styles}")
    # Add wishes lines:
    if req.travel_description:
        lines.append(f"Reisebeschreibung: {req.travel_description}")
    if req.preferred_activities:
        lines.append(f"Bevorzugte Aktivitäten: {', '.join(req.preferred_activities)}")
    if req.mandatory_activities:
        acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
        lines.append(f"Pflichtaktivitäten: {', '.join(acts)}")
    ...
```

### Pattern 5: StopOptionsFinderAgent — Inline in _build_prompt()

StopOptionsFinderAgent builds the prompt in `_build_prompt()`. The wishes block belongs after the `style_emphasis` block and before `rules_block`. Add three conditional lines and interpolate after `{style_emphasis}`:

```python
desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
mandatory_line = f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""
```

### Pattern 6: Frontend Tag-Chip Input (duplicate mandatoryTags)

The existing mandatoryTags pattern in `form.js`:
- State: `S.mandatoryTags: []`
- HTML element IDs: `mandatory-tag-input`, `mandatory-tags`
- JS functions: `addTagFromInput()`, `renderTags()`, `removeTag(idx)`
- buildPayload: `mandatory_activities: S.mandatoryTags.map(name => ({ name }))`
- Cache key: `mandatoryTags`

The preferred_activities pattern mirrors this:
- State: `S.preferredTags: []`
- HTML element IDs: `preferred-tag-input`, `preferred-tags`
- JS functions: `addPreferredTagFromInput()`, `renderPreferredTags()`, `removePreferredTag(idx)`
- buildPayload: `preferred_activities: S.preferredTags` (already a list of strings, not objects)
- Cache key: `preferredTags`

### Pattern 7: Frontend localStorage Cache/Restore

`saveFormToCache()` in form.js currently saves:
```javascript
lsSet(LS_FORM, { ...p, travelStyles: S.travelStyles, children: S.children, mandatoryTags: S.mandatoryTags });
```

Add `preferredTags: S.preferredTags` to this object.

`restoreFormFromCache()` currently has:
```javascript
if (cached.mandatoryTags) {
  S.mandatoryTags = cached.mandatoryTags;
  renderTags();
}
```

Add analogous block for `preferredTags`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tag input UI | Custom JS widget | Mirror mandatoryTags pattern exactly | Already tested in prod; consistent UX |
| Context forwarding | Custom middleware/hook | Direct f-string interpolation in each agent | No abstraction layer needed; prompts are per-agent |
| State persistence | Custom serialization | `lsSet`/`lsGet` in state.js, `LS_FORM` key | Already used for all form state |

---

## Common Pitfalls

### Pitfall 1: buildPayload() already hardcodes `preferred_activities: []`

**What goes wrong:** `buildPayload()` at line 762 already has `preferred_activities: []` — a hardcoded empty array. If left unchanged after adding the UI, the array is never populated.
**Why it happens:** This was a placeholder added when the model was defined but the UI wasn't built yet.
**How to avoid:** Change line 762 to `preferred_activities: S.preferredTags` when wiring up the new tag input.
**Warning signs:** Logs show `preferred_activities: []` even when user entered tags.

### Pitfall 2: Prompt injection position matters

**What goes wrong:** If the wishes block is inserted after the JSON schema/rules section, Claude may treat it as part of the schema.
**Why it happens:** Prompt structure confusion — instructions after schema can be ignored or cause malformed JSON.
**How to avoid:** Always insert wishes lines before the JSON schema example and rules block, immediately after the request context parameters (travelers, styles, dates).
**Warning signs:** Agent returns unexpected JSON fields or ignores wishes.

### Pitfall 3: mandatory_activities formatting differs between agents

**What goes wrong:** Some agents use `a.name` only (ActivitiesAgent `mandatory_line`), while RouteArchitect uses `a.name + (a.location)`. The ActivitiesAgent pattern drops location — acceptable for most agents, but StopOptionsFinder benefits from location context.
**Why it happens:** The MandatoryActivity model has `name` + optional `location`. Location is relevant to route planning (where to go) but less relevant to activities/restaurants (what to do there).
**How to avoid:** For routing agents (RouteArchitect, StopOptionsFinder, RegionPlanner, DayPlanner), include location. For content agents (Accommodation, Restaurants, TravelGuide, TripAnalysis), name-only is fine.
**Verified:** `MandatoryActivity.location` is `Optional[str]` — code must guard against None.

### Pitfall 4: preferred_activities is `List[str]`, mandatory_activities is `List[MandatoryActivity]`

**What goes wrong:** Using the wrong join expression — e.g., `', '.join(req.preferred_activities)` is correct; `', '.join(req.mandatory_activities)` would fail because MandatoryActivity is not a string.
**How to avoid:** Follow the ActivitiesAgent template exactly: `', '.join(req.preferred_activities)` for preferred (list of strings) and `', '.join(a.name for a in req.mandatory_activities)` for mandatory (list of objects).

### Pitfall 5: Frontend renderTags / renderPreferredTags diverge if refactored together

**What goes wrong:** Attempting to unify both into a single generic function requires passing IDs as arguments — increases complexity with minimal gain.
**How to avoid:** Keep them as separate functions (same pattern, different element IDs). Duplication here is fine — 20 lines each.

### Pitfall 6: travel_description placeholder not updated in index.html

**What goes wrong:** The textarea `#travel-description` already exists in Step 2 (line 268 of index.html) with placeholder "Was soll diese Reise besonders machen?" — D-05 specifies a richer placeholder.
**How to avoid:** Update the placeholder attribute on the existing textarea; do not add a new textarea element.

---

## Code Examples

### Reference: ActivitiesAgent wishes block (complete, verified)
```python
# Source: backend/agents/activities_agent.py lines 183-185
# Optionale Kontextblöcke
desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
mandatory_line = f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""
```

Then interpolated in the prompt at line 201:
```python
Aktivitätenbudget: ca. CHF {budget_per_stop:.0f}...{mandatory_line}{pref_line}{desc_line}{style_guidance}
```

### Frontend: New state field
```javascript
// Source: frontend/js/state.js — add to S object alongside mandatoryTags
preferredTags: [],
```

### Frontend: New buildPayload() line
```javascript
// Source: frontend/js/form.js line 762 — replace hardcoded empty array
preferred_activities: S.preferredTags,
```

### Frontend: New cache save (form.js saveFormToCache)
```javascript
lsSet(LS_FORM, { ...p, travelStyles: S.travelStyles, children: S.children,
  mandatoryTags: S.mandatoryTags, preferredTags: S.preferredTags });
```

### Frontend: New HTML block for Step 2 (after travel-description group, before form-nav)
```html
<div class="form-group">
  <label>Bevorzugte Aktivitäten (optional)</label>
  <div class="tag-input-row">
    <input type="text" id="preferred-tag-input"
      placeholder="z.B. Weinproben, Wandern, Museumsbesuche"
      onkeydown="if(event.key==='Enter'){addPreferredTagFromInput();event.preventDefault()}">
    <button class="btn btn-secondary" onclick="addPreferredTagFromInput()">Hinzufügen</button>
  </div>
  <div class="tags-container" id="preferred-tags"></div>
</div>
```

---

## File-by-File Change Map

Exact locations for every change to be made, derived from reading the source code.

### Backend Agent Files

| File | What to Change | Insertion Point |
|------|---------------|-----------------|
| `agents/route_architect.py` | Add `pref_str` conditional + `{pref_str}` in prompt | After `mandatory_str` block (line ~51); insert in prompt after `{mandatory_str}` (line ~126) |
| `agents/stop_options_finder.py` | Add all 3 conditional lines + interpolate in prompt | After `style_emphasis` block (~line 200); insert before `{rules_block}` |
| `agents/region_planner.py` | Add all 3 fields in `_leg_context()` | After `lines.append(f"Reisestile: {styles}")` (~line 137) |
| `agents/accommodation_researcher.py` | Add all 3 conditional lines + interpolate in prompt | After `extra_hint` block (~line 88); insert after `{extra_hint}` in prompt |
| `agents/restaurants_agent.py` | Add all 3 conditional lines + interpolate in prompt | After `real_data_block` setup; insert before or after `Reisestile:` line in prompt |
| `agents/day_planner.py` | Add all 3 conditional lines + interpolate in prompt | After `ferry_info` block; insert in prompt after `Reisende:` line |
| `agents/travel_guide_agent.py` | Add all 3 conditional lines + interpolate in prompt | After `wiki_block` setup; insert in prompt after `Reisestile:` line |
| `agents/trip_analysis_agent.py` | Add `travel_description` + `preferred_activities` to prompt | Inside the `## Benutzeranforderungen` block, after `Pflichtaktivitäten:` line |

### Frontend Files

| File | What to Change |
|------|---------------|
| `frontend/js/state.js` | Add `preferredTags: []` to S object (after `mandatoryTags: []`, line 39) |
| `frontend/js/form.js` | (1) Add `addPreferredTagFromInput()`, `renderPreferredTags()`, `removePreferredTag()` functions; (2) Wire `preferred_activities: S.preferredTags` in `buildPayload()`; (3) Add `preferredTags: S.preferredTags` to `saveFormToCache()`; (4) Add restore block for `preferredTags` in `restoreFormFromCache()` |
| `frontend/index.html` | (1) Update `travel-description` placeholder (Step 2, line 268); (2) Add preferred-activities tag-chip input block to Step 2 (after travel-description group, before form-nav) |

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — pure code changes within existing stack)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `backend/pytest.ini` or none (discovered automatically) |
| Quick run command | `cd backend && python3 -m pytest tests/test_agents_mock.py -v -x` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CTX-01 | preferred_activities tag input renders, adds tags to S.preferredTags | manual smoke | browser check | N/A (frontend) |
| CTX-02 | travel_description + preferred_activities appear in agent prompts | unit | `pytest tests/test_agents_mock.py -v -x` | ✅ existing |
| CTX-02 | buildPayload() populates preferred_activities from S.preferredTags | manual smoke | browser check | N/A (frontend) |
| CTX-03 | mandatory_activities appear in StopOptionsFinder prompt | unit | `pytest tests/test_agents_mock.py -v -x` | ✅ existing |

### Sampling Rate

- **Per task commit:** `cd backend && python3 -m pytest tests/test_agents_mock.py -v -x`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

New test cases to add to `tests/test_agents_mock.py`:

- [ ] `test_route_architect_includes_preferred_activities` — verify `preferred_activities` appears in RouteArchitect prompt when set
- [ ] `test_stop_options_finder_includes_all_wishes` — verify all 3 fields appear in StopOptionsFinder `_build_prompt()` when set
- [ ] `test_wishes_absent_when_empty` — verify no extra lines when all 3 fields are empty/default
- [ ] `test_restaurants_agent_includes_wishes` — verify wishes appear in RestaurantsAgent prompt

These follow the existing pattern in `test_agents_mock.py` (mock Anthropic client, call agent, assert prompt contains expected substrings).

---

## Project Constraints (from CLAUDE.md)

Directives the planner must verify:

| Directive | Impact on This Phase |
|-----------|---------------------|
| All user-facing text in German | New HTML labels, placeholders, form hints must be German |
| Prices always in CHF | No price fields added in this phase — not applicable |
| TEST_MODE=true uses claude-haiku-4-5 | No model changes in this phase — not applicable |
| Agents always return valid JSON | Prompt additions must not corrupt JSON schema section |
| `call_with_retry()` for all Claude calls | No new Claude calls added — existing wrappers remain |
| `parse_agent_json()` for all JSON parsing | No new parsing — existing code handles it |
| All API calls logged with `debug_logger.log(LogLevel.API, ...)` | No new API calls in this phase |
| `esc()` for all user content in HTML interpolation | `preferred_activities` from server goes into DOM — must use `esc()` if displayed |
| `S` object for global state | New `preferredTags` must be on S, not module-level |
| API calls only in `api.js` | No new API calls in frontend |
| localStorage keys prefixed `tp_v1_*` | `LS_FORM` key already handles this — check that `preferredTags` serializes inside existing key |

---

## Open Questions

1. **Where exactly in Step 2 should `preferred_activities` appear?**
   - What we know: D-03 says all wishes fields in Step 2; `travel_description` is already at the bottom of Step 2; `preferred_activities` should be near `travel_description` (both are "what" context)
   - What's unclear: Whether preferred_activities goes above or below travel_description
   - Recommendation: Place preferred_activities immediately below travel_description and above the form-nav buttons. This groups both "wish" inputs together at the bottom of Step 2, after the structural choices (adults, children, styles).

2. **Should `preferred_activities` also appear in the Step 5 Summary (`renderSummary()`)?**
   - What we know: `mandatory_activities` is shown in the summary (line 810 of index.html)
   - What's unclear: CONTEXT.md does not mention summary display
   - Recommendation: Add `preferred_activities` to summary display analogously to mandatory_activities — same pattern, separate line. Low risk, good UX.

---

## Sources

### Primary (HIGH confidence)

All findings are based on direct reading of the project source code — no external library research needed.

- `backend/agents/activities_agent.py` — canonical reference implementation (lines 183-185, 200-201)
- `backend/agents/route_architect.py` — partial implementation to extend (lines 47-50, 122, 126)
- `backend/agents/trip_analysis_agent.py` — partial implementation to extend (lines 42-57)
- `backend/models/travel_request.py` — field definitions, types, validation constraints
- `frontend/js/form.js` — buildPayload, tag input pattern, cache/restore logic
- `frontend/js/state.js` — S object, mandatoryTags definition
- `frontend/index.html` — Step 2 and Step 3 HTML structure

### Secondary (MEDIUM confidence)

- All remaining 5 agent files read directly — insertion points confirmed by reading actual source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all changes within existing patterns
- Architecture patterns: HIGH — copied directly from working reference implementation in codebase
- Pitfalls: HIGH — discovered by reading actual code (hardcoded `[]`, existing placeholder, type differences)

**Research date:** 2026-03-29
**Valid until:** Until any agent prompt structure or form.js buildPayload() changes
