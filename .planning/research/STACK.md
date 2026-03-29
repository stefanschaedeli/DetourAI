# Stack Research

**Domain:** AI route planning quality — day distribution, agent context, budget management, map viewport
**Researched:** 2026-03-28
**Confidence:** HIGH

> This research covers ONLY what v1.2 adds. The existing stack (FastAPI, vanilla JS, Google Maps JS SDK,
> Redis, Celery, Docker, Anthropic SDK, aiohttp) is validated and not re-evaluated.

---

## Summary Answer: No New Libraries Required

All v1.2 capabilities are achievable with the existing stack. The changes are algorithmic (Python logic
in existing agents/utilities), prompt engineering (structured context blocks added to agent prompts),
and frontend-side vanilla JS/CSS (map viewport calls, tooltip attributes). Zero new pip packages, zero
new JS libraries.

---

## Recommended Stack

### Core Technologies (Already Present — Extend, Don't Replace)

| Technology | Current Use | v1.2 Extension | Confidence |
|------------|-------------|----------------|------------|
| Python stdlib `math` | `math.sqrt` in maps_helper | Weighted night distribution formula — `math.ceil/floor` for integer allocation | HIGH |
| Anthropic SDK `>=0.28.0` | All 9 agents via `call_with_retry()` | Add `cache_control` block on static system prompts for stop_options_finder (prompt caching). No version bump needed — feature available in current SDK. | HIGH |
| Google Maps JS SDK (raster) | `fitBounds()` in maps.js + guide-map.js | Auto-fit bounds on route-builder open (extend `_setupRouteMap`) + after stop selection | HIGH |
| Pydantic `>=2.7.0` | All API models | Extend `TravelRequest` with optional `global_wishes: str` field (max 500 chars) | HIGH |
| CSS `title` attribute | Scattered `title=""` on buttons | Native tooltip via `title=""` is sufficient for edit/adjust buttons — no library needed | HIGH |
| Redis + job state dict | All job fields in `job:{job_id}` | Add `selected_stop_names: list[str]` key to track history across stop-selection calls | HIGH |

### What Each v1.2 Feature Needs Technically

#### 1. Intelligent Day/Night Distribution

**What it is:** RouteArchitect currently assigns nights with a simple min/max range. v1.2 needs to weight nights by destination potential (major city vs transit stop) to avoid under-spending at high-value stops.

**Implementation pattern — pure Python, no library:**

```python
def distribute_nights(total_nights: int, stops: list[dict],
                      min_nights: int, max_nights: int) -> list[int]:
    """
    Weight nights proportionally to stop_potential score (1-3 scale).
    Claude already assigns stop_potential in the route JSON.
    """
    weights = [s.get("stop_potential", 2) for s in stops]
    total_weight = sum(weights)
    raw = [total_nights * w / total_weight for w in weights]
    # Integer allocation with floor + distribute remainder to highest-potential stops
    floored = [max(min_nights, min(max_nights, math.floor(r))) for r in raw]
    remainder = total_nights - sum(floored)
    fractional = sorted(range(len(raw)), key=lambda i: raw[i] - math.floor(raw[i]), reverse=True)
    for i in fractional[:remainder]:
        floored[i] = min(max_nights, floored[i] + 1)
    return floored
```

**Where it lives:** New utility function in `backend/utils/route_utils.py` (new file) OR directly in `RouteArchitectAgent._build_prompt()` as a post-processing step. The agent prompt already includes `stop_potential` in the output schema — the distribution logic validates and corrects the AI's output.

**Confidence:** HIGH — this is arithmetic over the route JSON Claude already returns. No external library needed.

#### 2. Agent Context/History Passing (Stop Finder History Awareness)

**What it is:** `StopOptionsFinderAgent` already passes `selected_stops` as a compact list of names. The gap is that Claude sees them as a label string but may still suggest duplicates or stylistically similar options. The fix is a more structured "already visited" block + explicit exclusion instruction.

**Current pattern (already works, needs tightening):**

```python
# In stop_options_finder.py _build_prompt()
stops_str = "Bisherige Stopps: " + ", ".join(parts)
```

**v1.2 pattern — structured exclusion block:**

```python
already_visited = [s["region"] for s in selected_stops]
exclusion_block = (
    f"\nBEREITS AUSGEWÄHLT (NICHT WIEDERHOLEN): {', '.join(already_visited)}\n"
    f"Keine Option darf geografisch innerhalb 80 km eines bereits ausgewählten Stopps liegen.\n"
)
```

**Why no new framework:** The Anthropic Messages API is stateless — each call sends the full context. The existing `selected_stops` list IS the history. The improvement is prompt engineering, not architecture. (Source: Anthropic context engineering guide — "passing structured history in the system/user turn is the canonical pattern.")

**Prompt caching opportunity:** The RouteArchitect system prompt is static (400+ tokens). Adding `cache_control: {"type": "ephemeral"}` to the system message block reduces cost by ~90% on repeated calls during the same planning session. Supported in current `anthropic>=0.28.0` SDK.

```python
# Pattern for adding prompt caching to any agent:
response = client.messages.create(
    model=self.model,
    system=[{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}  # 5-min TTL, 1.25x write cost, 0.1x read cost
    }],
    messages=[{"role": "user", "content": user_prompt}],
    max_tokens=max_tokens,
)
```

**Confidence:** HIGH — documented feature in current SDK version, well-tested in production by Anthropic.

#### 3. Budget Management and Distribution

**What it is:** Budget percentages (accommodation/food/activities) are already stored in `TravelRequest`. The gap is that per-stop budget calculations use `total_days` evenly but ignore the actual `nights` distribution — a 1-night transit stop gets the same food budget as a 4-night destination. Fix is arithmetic adjustments using actual nights from the resolved route.

**Implementation:** Adjust `ActivitiesAgent`, `RestaurantsAgent`, and `AccommodationResearcherAgent` to use `stop.get("nights", min_nights)` (already done) but also to pass a total nights sum so fractional budget is correct:

```python
# In ActivitiesAgent (already uses nights — verify consistency):
total_nights = sum(s.get("nights", req.min_nights_per_stop) for s in stops)
budget_per_night = req.budget_chf * (req.budget_activities_pct / 100) / max(1, total_nights)
budget_for_stop = budget_per_night * stop_nights
```

**Tage-Neuberechnung trigger:** When nights change (via the `prompt()` nights-edit already in v1.1), the day plan needs recalculation. This requires a lightweight `POST /api/travels/{id}/recalculate-days` endpoint that re-runs `DayPlannerAgent` on the modified stop list. Pattern already exists for `replace_stop` — mirror it.

**No new library:** Pure arithmetic in existing agent code. No optimization solver needed.

**Confidence:** HIGH — arithmetic only, pattern already exists in codebase.

#### 4. Map Viewport Management

**What it is:** Two specific gaps identified in v1.2 requirements:
1. Travel view opens with default zoom (Switzerland area), not fitted to route
2. Route-builder: zoom should show all selected stops + new options, not just new options

**Implementation — extend existing `fitBounds()` calls:**

`fitBounds(bounds, padding)` already works in the codebase (lines 689, 749, 811 in maps.js). The padding parameter accepts both a number and an object `{top, right, bottom, left}` — confirmed by Google Maps JS API reference (HIGH confidence from official docs fetch).

**Gap 1 fix — travel view auto-fit:**

```javascript
// In guide-map.js _initGuideMap(), after all markers added:
if (hasBounds) {
  map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  // ← This already exists. The bug is timing: called before map is fully ready.
  // Fix: wrap in google.maps.event.addListenerOnce(map, 'idle', () => {...})
}
```

**Gap 2 fix — route-builder viewport includes history:**

```javascript
// In route-builder.js _renderOptions(), extend bounds to include already-selected stops:
const allPoints = [...selectedStops.map(s => ({lat: s.lat, lng: s.lng})),
                   ...options.map(o => ({lat: o.lat, lng: o.lon}))];
const bounds = allPoints.reduce((b, p) => b.extend(p), new google.maps.LatLngBounds());
map.fitBounds(bounds, { top: 60, right: 40, bottom: 40, left: 40 });
```

**Confidence:** HIGH — `fitBounds` with padding object is confirmed in Google Maps JS API reference. Pattern already used at 3 locations in maps.js.

#### 5. Global Wishes Field in Trip Form

**What it is:** A new optional free-text field on the trip form (`global_wishes`) that gets passed verbatim to all agents. Different from `travel_description` (about style/context) — this is specific user instructions ("avoid motorways", "include wine regions", "stop near Michelin restaurants").

**Implementation:**

```python
# In TravelRequest (models/travel_request.py):
global_wishes: Optional[str] = Field(default=None, max_length=500)
```

Pass to each agent prompt as a dedicated block:
```python
wishes_block = f"\nNUTZERWÜNSCHE: {req.global_wishes}\n" if req.global_wishes else ""
```

**Frontend:** Single `<textarea>` in the form step (step 1 or step 5), max 500 chars, with character counter. Vanilla JS, no library.

**Confidence:** HIGH — trivial model + UI change.

#### 6. Tooltips for Edit Buttons

**What it is:** Edit, replace, remove, and "adjust nights" buttons on stop cards currently have `title=""` attributes (confirmed in `guide-stops.js:189-193`). The native browser tooltip is sufficient for desktop. Mobile users don't hover, so tooltip is not critical.

**Recommendation:** Use native `title=""` attribute (already present on some buttons, just needs consistent application). No JS tooltip library needed.

**If custom styling is desired:** A pure CSS tooltip using `[data-tooltip]::after` pseudo-element with `content: attr(data-tooltip)` is zero-dependency and already a standard pattern. ~15 lines of CSS.

```css
[data-tooltip] { position: relative; }
[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute; bottom: 110%; left: 50%; transform: translateX(-50%);
  background: #333; color: #fff; padding: 4px 8px; border-radius: 4px;
  font-size: 12px; white-space: nowrap; pointer-events: none;
  opacity: 0; transition: opacity 0.15s;
}
[data-tooltip]:hover::after { opacity: 1; }
```

**Confidence:** HIGH — CSS-only, no browser incompatibilities, zero dependencies.

#### 7. Hotel Geheimtipps: Distance Enforcement

**What it is:** `is_geheimtipp: true` options are already distance-limited by the prompt instruction (`hotel_radius_km`), but the enforcement is only in the prompt — no backend validation. Add a Python guard that checks the geheimtipp's coordinates against the stop's geocoded position.

**Implementation:**

```python
import math

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))
```

This 6-line function (no library) is already the right tool. `math` is stdlib. No new dependency.

**Confidence:** HIGH — stdlib math only.

---

## Installation

```bash
# Backend: ZERO new packages
# requirements.txt unchanged

# Frontend: ZERO new libraries
# index.html script tags unchanged
# No CDN additions

# New backend file (utility only):
# backend/utils/route_utils.py  ← day distribution helper
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| Pure Python arithmetic for night distribution | OR-Tools / scipy.optimize | Massive overkill. The problem is bounded integer allocation with weights — 10 lines of Python with `math.floor`. OR-Tools would add 50MB to the Docker image. |
| Structured exclusion block in prompt for history | Vector embeddings + semantic dedup | Overkill for ~10 stop names. String comparison is sufficient. Embeddings require a new service or API call. |
| CSS `[data-tooltip]` pseudo-element | Tippy.js / Floating UI | ~5KB vs 0KB. The project has zero JS dependencies in the frontend. Adding a tooltip library to a vanilla JS project is scope creep. |
| Anthropic prompt caching (`cache_control`) | Context window management / summarization | Prompt caching is the right tool for repeated static system prompts. No compression needed — the context is already small. |
| `map.fitBounds()` with `'idle'` listener | Manual timeout / `setTimeout` delay | `'idle'` is the correct Google Maps event for "map is fully rendered and ready for viewport changes". Timeout-based approaches produce jank. |
| Haversine in `utils/route_utils.py` (stdlib math) | `geopy` / `haversine` package | 6 lines of stdlib vs a new pip dependency. The formula is well-known and needs no abstraction. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `scipy` / `numpy` for distribution math | Night distribution is bounded integer arithmetic — no optimization solver needed. These packages add ~50MB to the Docker image. | `math.floor`, `math.ceil`, and a sort with index tracking |
| OR-Tools / route optimization libraries | v1.2 is about AI prompt quality and UI fixes, not route graph optimization. The AI (Claude Opus) IS the route optimizer. | Better-structured prompts to `RouteArchitectAgent` |
| `tippy.js` or any tooltip library | Zero benefit over CSS `[data-tooltip]::after`. Adds network request + init JS. | CSS pseudo-element tooltip (15 lines) |
| `langchain` / `llama-index` / agent frameworks | The project has a clean, well-tested custom agent pattern. LangChain would add a large dependency graph and obscure the agent logic behind abstractions the team doesn't control. | Current `call_with_retry()` + `parse_agent_json()` pattern |
| SQLite full-text search extension | Stop history deduplication works on a list of ~10 names — no search index needed. | Simple Python list membership check (`region not in already_visited`) |
| Websockets to replace SSE | SSE is simpler, unidirectional, and already deployed with Nginx + Celery. No bidirectional communication is needed for v1.2. | Extend existing SSE event types |

---

## Version Compatibility

All changes are within already-pinned dependency versions:

| Package | Current Pin | v1.2 Feature Used | Notes |
|---------|-------------|-------------------|-------|
| `anthropic>=0.28.0` | >=0.28.0 | `cache_control` on system messages | Prompt caching available since 0.25+. No version bump needed. |
| `pydantic>=2.7.0` | >=2.7.0 | `Optional[str]` field on `TravelRequest` | Standard Pydantic v2 pattern. |
| Google Maps JS SDK | Weekly auto-updated CDN | `fitBounds(bounds, {top,right,bottom,left})` | Padding object supported since 2017 per official docs. Already used in codebase. |
| Python `math` | stdlib | `floor`, `ceil`, `sqrt`, `radians` | No changes. |

---

## Sources

- Google Maps JS API reference `Map.fitBounds()` — padding accepts `number | Padding` object; codebase already uses `{top:40, right:40, bottom:40, left:40}` at 3 locations (HIGH confidence — verified in maps.js)
- [Anthropic Prompt Caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — `cache_control: {"type": "ephemeral"}` on system messages, 5-min TTL, 90% cost reduction for static prefixes (HIGH confidence — official docs)
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — structured history in user turn is canonical pattern; "just-in-time" context is preferred over pre-loading (HIGH confidence — official Anthropic engineering blog)
- Codebase analysis — `backend/agents/stop_options_finder.py:55-63` (existing history passing), `backend/agents/accommodation_researcher.py:96-129` (geheimtipp radius enforcement), `frontend/js/guide-map.js:39-90` (fitBounds timing), `frontend/js/maps.js:615-650` (fitBounds with padding) — verified existing patterns (HIGH confidence)
- [Google Maps: `idle` event](https://developers.google.com/maps/documentation/javascript/reference/map#Map.idle) — fires after map viewport is fully rendered, correct hook for post-init `fitBounds` (HIGH confidence — official docs)

---
*Stack research for: v1.2 AI route quality — day distribution, agent context, budget, map viewport*
*Researched: 2026-03-28*
