# Phase 1: AI Quality Stabilization - Research

**Researched:** 2026-03-25
**Domain:** AI agent prompt engineering, coordinate validation, route quality checks
**Confidence:** HIGH

## Summary

This phase addresses five quality problems in the AI stop-finding pipeline. The codebase already has most infrastructure needed: geocoding, haversine distance, corridor bounding boxes, Google Places API, SSE event system, and a retry mechanism. The primary work is (1) a one-line model bug fix, (2) adding post-validation layers for coordinates, travel style, stop quality, and route bearing, and (3) a new plausibility challenge flow in RouteArchitect with a corresponding frontend SSE handler.

The existing `_find_and_stream_options()` function in `main.py` (line 680+) already filters options by proximity and overshoot. The new validations (corridor check, bearing check, Google Places quality check) plug into this same function as additional validation steps after geocoding. The travel style enforcement requires prompt modifications in both `route_architect.py` and `stop_options_finder.py`. The plausibility challenge is a new step in RouteArchitect that fires before any stop selection begins.

**Primary recommendation:** Layer new validation checks into the existing `_enrich_one()` function in `main.py` and modify agent prompts for style enforcement. Keep the validation pipeline order: geocode -> proximity -> overshoot -> corridor -> bearing -> quality (Google Places). Silent replacement on quality failure; visual flag on corridor failure.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Fix `backend/agents/stop_options_finder.py:33` -- change hardcoded `"claude-haiku-4-5"` to `"claude-sonnet-4-5"` as the production model
- **D-02:** Validate all geocoded stop coordinates against the route corridor bounding box after Claude suggests them
- **D-03:** Corridor width is proportional to leg distance (e.g. 20% of the leg distance). Short legs get tight corridors, long legs allow more exploration
- **D-04:** When a stop falls outside the corridor: flag it visually to the user but still show it. Do NOT silently reject
- **D-05:** Travel style is a weighted preference, not an absolute filter. 2 of 3 stop options must match the requested style. 1 can be a "wildcard"
- **D-06:** Style enforcement happens at both RouteArchitect and StopOptionsFinder levels. Double reinforcement
- **D-07:** After Claude suggests a stop, validate it against Google Places API. If the place has no results, very low rating, or is clearly wrong category, it's low-quality
- **D-08:** When a low-quality stop is detected: silently re-ask Claude for a replacement. User only sees good options
- **D-09:** Detect zigzag/backtracking via bearing check between stops. If a stop reverses direction significantly (>90 degree deviation from overall route bearing), it's backtracking
- **D-10:** Use both prevention and post-validation for route efficiency. Prevention: include previous stop coordinates and route bearing in StopOptionsFinder prompt. Post-validation: check bearing after suggestion
- **D-11:** When travel style preferences don't match the destination geography, the RouteArchitect challenges the request early -- before stop selection begins
- **D-12:** Challenge appears as an SSE message with suggestion in German. User can adjust or continue
- **D-13:** This is a new SSE event type (`style_mismatch_warning`) that the frontend must handle. If user doesn't respond / continues, proceed with best-available stops

### Claude's Discretion
- Exact corridor width percentage (20% suggested but Claude can tune based on testing)
- Google Places quality threshold (minimum rating, minimum review count)
- Bearing deviation threshold for backtracking (90 degrees suggested but can be refined)
- Maximum number of retry attempts when re-asking Claude for replacements (suggest 2 retries max)
- Exact wording of the German-language plausibility challenge messages

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AIQ-01 | StopOptionsFinder uses correct production model (claude-sonnet-4-5) | One-line fix at `stop_options_finder.py:33`. Change `"claude-haiku-4-5"` to `"claude-sonnet-4-5"`. `get_model()` already handles TEST_MODE fallback. |
| AIQ-02 | All geocoded stop coordinates validated against route corridor bounding box | Existing `corridor_bbox()` in `maps_helper.py` and `_enrich_one()` in `main.py` provide the hook point. Add proportional corridor width + flag logic. |
| AIQ-03 | Stop finder prompts enforce user's travel style preference | Modify prompts in both `route_architect.py` and `stop_options_finder.py`. Add 2/3 matching rule to prompt + post-validation. |
| AIQ-04 | Stop suggestions maintain consistent quality | Use `find_place_from_text()` from `google_places.py` for validation. Silent re-ask via existing retry pattern. |
| AIQ-05 | Route architect produces driving-efficient routes without zigzag | Add bearing calculation utility, include bearing context in prompts, post-validate with bearing check in `_enrich_one()`. |
</phase_requirements>

## Standard Stack

No new libraries required. All functionality uses existing dependencies.

### Core (already installed)
| Library | Purpose | Used For |
|---------|---------|----------|
| FastAPI | HTTP framework | Existing -- endpoints, SSE |
| anthropic SDK | Claude API | Existing -- all agent calls |
| aiohttp | Async HTTP | Existing -- Google API calls |
| Pydantic | Validation | Existing -- models |

### Utilities (already available in codebase)
| Utility | File | Used For |
|---------|------|----------|
| `geocode_google()` | `utils/maps_helper.py` | Resolve stop names to coordinates |
| `haversine_km()` | `utils/maps_helper.py` (also `main.py:465`) | Distance calculations for corridor/bearing |
| `corridor_bbox()` | `utils/maps_helper.py:206` | Bounding box for route sections |
| `find_place_from_text()` | `utils/google_places.py:100` | Quality validation against Google Places |
| `nearby_search()` | `utils/google_places.py:12` | Alternative quality check (rating, reviews) |
| `call_with_retry()` | `utils/retry_helper.py` | Retry pattern for re-asking Claude |
| `debug_logger.push_event()` | `utils/debug_logger.py` | SSE event emission for new event types |
| `decode_polyline5()` | `utils/maps_helper.py:153` | Route geometry for corridor checks |
| `point_along_route()` | `utils/maps_helper.py:188` | Find points on route at specific distances |

## Architecture Patterns

### Validation Pipeline (insertion points in `_enrich_one()` in `main.py`)

Current validation order in `_enrich_one()` (starting at line 784):
```
1. Geocode place via Google
2. Get Google Directions (drive_hours, drive_km)
3. Proximity check: too close to origin?  -> return None (reject)
4. Proximity check: too close to target?  -> return None (reject)
5. Overshoot check: further than target?  -> return None (reject)
```

New validation steps to add AFTER the existing ones:
```
6. Corridor check: inside proportional corridor?  -> FLAG (D-04: show with warning, do NOT reject)
7. Bearing check: backtracking detected?          -> return None (reject, trigger re-ask)
8. Quality check: Google Places validation         -> return None (reject, trigger silent re-ask)
```

Key distinction: corridor violations are FLAGGED (user sees them with a warning badge), while bearing violations and quality failures cause SILENT REJECTION with re-ask.

### New Fields on StopOption Model

```python
# Add to backend/models/stop_option.py StopOption class:
outside_corridor: bool = False      # True when stop is outside proportional corridor
corridor_distance_km: Optional[float] = None  # How far outside the corridor (for display)
travel_style_match: bool = True     # True when stop matches requested travel style
```

### Bearing Calculation Utility

```python
import math

def bearing_degrees(from_coord: tuple[float, float], to_coord: tuple[float, float]) -> float:
    """Calculate initial bearing from from_coord to to_coord in degrees (0-360)."""
    lat1, lon1 = math.radians(from_coord[0]), math.radians(from_coord[1])
    lat2, lon2 = math.radians(to_coord[0]), math.radians(to_coord[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

def bearing_deviation(bearing1: float, bearing2: float) -> float:
    """Absolute angular difference between two bearings (0-180)."""
    diff = abs(bearing1 - bearing2) % 360
    return min(diff, 360 - diff)
```

This goes into `utils/maps_helper.py` alongside the existing `haversine_km()`.

### Proportional Corridor Width (D-03)

```python
def proportional_corridor_buffer(leg_distance_km: float) -> float:
    """Buffer in km = 20% of leg distance, clamped to [15, 100] km."""
    buffer = leg_distance_km * 0.20
    return max(15.0, min(buffer, 100.0))
```

For a 200km leg: 40km buffer. For a 500km leg: 100km buffer (capped). For a 50km leg: 15km buffer (floor).

### Plausibility Challenge Flow (D-11, D-12, D-13)

```
1. User submits trip request
2. RouteArchitect.run() is called
3. NEW: Before generating route, RouteArchitect checks if travel_styles
   match destination geography (add to system prompt)
4. If mismatch detected: RouteArchitect returns JSON with "plausibility_warning" field
5. Backend emits SSE event type "style_mismatch_warning" with warning text + suggestions
6. Frontend shows warning banner with "Trotzdem weiter" button
7. Backend proceeds immediately (fire-and-forget) -- warning is informational only
8. If user wants to adjust: they go back to form and re-submit
```

RouteArchitect prompt addition:
```
PLAUSIBILITAETSPRUEFUNG: Pruefe ob die angegebenen Reisestile ({travel_styles})
geographisch zum Zielgebiet passen. Wenn ein Reisestil im Zielgebiet nicht
umsetzbar ist (z.B. "Vulkane" in Frankreich, "Strand" in den Alpen), fuege
ein "plausibility_warning" Feld hinzu mit einer Erklaerung und Alternativen.
```

### SSE Event Types (new)

| Event Type | Data Shape | Handler |
|------------|-----------|---------|
| `style_mismatch_warning` | `{warning: str, suggestions: str[], original_styles: str[]}` | Frontend: show warning banner |
| Existing: `route_option_ready` | Add `outside_corridor: bool` to option data | Frontend: render warning badge |

### Travel Style Enforcement in Prompts (D-05, D-06)

StopOptionsFinder prompt addition (after the existing `Reisestile:` line):
```
STIL-REGEL: Mindestens 2 der 3 Optionen MUESSEN dem Reisestil "{style}" entsprechen.
Die 3. Option darf ein interessanter "Wildcard"-Vorschlag sein, der nicht zum
Reisestil passt, aber fuer die Region besonders sehenswert ist.
Kennzeichne in jedem Vorschlag: "matches_travel_style": true/false
```

RouteArchitect prompt addition:
```
ROUTENPLANUNG NACH REISESTIL: Die Route soll durch Regionen fuehren, die zum
Reisestil "{styles}" passen. Beispiel: Bei "Strand" -> Kuestenroute bevorzugen.
Bei "Kultur" -> Route durch historisch bedeutsame Regionen.
```

### Google Places Quality Validation (D-07, D-08)

```python
async def validate_stop_quality(region: str, country: str, lat: float, lon: float) -> tuple[bool, str]:
    """Check stop quality via Google Places. Returns (is_quality, reason)."""
    # Strategy 1: Find Place From Text (cheapest API call)
    result = await find_place_from_text(f"{region}, {country}")
    if not result:
        return False, "Kein Google Places Ergebnis"

    # Strategy 2: Check nearby attractions (does this place have interesting things?)
    attractions = await nearby_search(lat, lon, "tourist_attraction", radius_m=5000)
    if len(attractions) < 2:
        return False, "Zu wenige Sehenswuerdigkeiten"

    # Strategy 3: Check if the place has reasonable quality
    rated = [a for a in attractions if a.get("rating")]
    if rated:
        avg_rating = sum(a["rating"] for a in rated) / len(rated)
        if avg_rating < 3.0:
            return False, f"Niedrige durchschnittliche Bewertung: {avg_rating:.1f}"

    return True, "OK"
```

Recommended thresholds (Claude's discretion):
- Minimum 2 tourist attractions within 5km radius
- Average rating >= 3.0 for nearby attractions
- Must have a Google Places result for `find_place_from_text()`
- Max 2 retry attempts when re-asking Claude for replacement

### Silent Re-ask Pattern (D-08)

When a stop fails quality validation, the system should:
1. Log the failure with `LogLevel.DEBUG`
2. NOT emit any SSE event about the failure
3. Call StopOptionsFinder again with extra instruction: `"Ersetze Option '{region}' -- Ort hat zu wenige Sehenswuerdigkeiten. Waehle einen bekannteren, touristisch relevanteren Ort in der gleichen Region."`
4. Max 2 retries per rejected stop
5. If all retries fail, show the original stop anyway (something is better than nothing)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Geocoding | Custom coordinate lookup | `geocode_google()` in `maps_helper.py` | Already cached, handles edge cases |
| Distance calculation | Simple lat/lon diff | `haversine_km()` in `maps_helper.py` | Great-circle distance is correct for route distances |
| Corridor bounding box | Manual lat/lon range | `corridor_bbox()` in `maps_helper.py` | Handles projection, buffer, and edge cases |
| Place validation | Name string matching | `find_place_from_text()` in `google_places.py` | Google Places is authoritative for place existence |
| SSE events | Custom WebSocket | `debug_logger.push_event()` | Existing SSE infrastructure handles cross-process (Celery) and in-process events |
| Retry logic | Manual loop with sleep | `call_with_retry()` in `retry_helper.py` | Handles 429, 529, exponential backoff, logging |

## Common Pitfalls

### Pitfall 1: Google API Cost Explosion
**What goes wrong:** Adding Google Places validation per stop option (3 options x N stops x retry attempts) multiplies API costs quickly.
**Why it happens:** Each `find_place_from_text()` costs $17/1000 calls. Each `nearby_search()` costs $32/1000.
**How to avoid:** Use `find_place_from_text()` as first-pass (cheap). Only call `nearby_search()` if the first check passes. Limit retries to 2 per rejected stop. Cache results.
**Warning signs:** Google Maps billing spikes. Add logging for Places API call counts per job.

### Pitfall 2: Corridor Check False Positives on Curved Routes
**What goes wrong:** A bounding box corridor check rejects valid stops on curved routes (e.g., coastal roads that curve inland).
**Why it happens:** `corridor_bbox()` is a rectangle, not a route-following shape.
**How to avoid:** D-04 already mitigates this -- corridor violations are FLAGGED, not rejected. The user can still select flagged stops. For the proportional buffer, use generous minimums (15km floor).
**Warning signs:** Too many stops getting flagged on mountain/coastal routes.

### Pitfall 3: Bearing Check Fails at Short Distances
**What goes wrong:** Bearing between two close points is unreliable (small coordinate differences amplify rounding errors).
**Why it happens:** `atan2` becomes noisy when both arguments are near zero.
**How to avoid:** Skip bearing check when distance between stops is < 20km. At short distances, zigzag is not a real problem anyway.
**Warning signs:** Valid nearby stops being rejected as "backtracking".

### Pitfall 4: Style Enforcement Creates Impossible Constraints
**What goes wrong:** Requesting "beach" style for an inland route (e.g., Liestal to Paris through the Alps) produces no valid stops because no beach stops exist on the route.
**Why it happens:** The 2/3 matching rule is too strict for routes that don't pass through style-matching regions.
**How to avoid:** The plausibility challenge (D-11) catches the worst cases early. For borderline cases, fall back to "best match" rather than strict enforcement. If Claude can't find 2/3 style-matching stops, accept 1/3 with a log warning.
**Warning signs:** Multiple retries failing to produce style-matching stops.

### Pitfall 5: Plausibility Challenge Blocks the Flow
**What goes wrong:** The `style_mismatch_warning` SSE event requires user interaction, but the user might not be watching the screen.
**Why it happens:** SSE is fire-and-forget from the backend perspective. There's no acknowledgment mechanism.
**How to avoid:** D-13 specifies: "If user doesn't respond / continues, proceed with best-available stops." Implement as fire-and-forget: backend emits warning and continues immediately. No timeout complexity needed.
**Warning signs:** Jobs stuck waiting for user response.

### Pitfall 6: Re-ask Loop Stalls the UX
**What goes wrong:** Silent re-asks for quality validation double or triple the time users wait for stop options.
**Why it happens:** Each re-ask is a full Claude API call (2-5 seconds with Sonnet).
**How to avoid:** Run quality validation in parallel with SSE emission. Show the first valid options immediately while quality-checking the rest. If a replacement is needed, emit a "replacing option" SSE event to update a specific card. Limit to 2 retries max.
**Warning signs:** Stop option loading time increasing from ~5s to ~15s.

## Code Examples

### Example 1: Model Bug Fix (AIQ-01)

```python
# backend/agents/stop_options_finder.py line 33
# BEFORE (bug):
self.model = get_model("claude-haiku-4-5", AGENT_KEY)

# AFTER (fix):
self.model = get_model("claude-sonnet-4-5", AGENT_KEY)
```

### Example 2: Corridor Validation in _enrich_one()

```python
# Inside _enrich_one() in main.py, after overshoot check:

# Corridor check: proportional buffer based on leg distance
segment_total_km = geo.get("segment_total_km", 0)
if segment_total_km > 0 and geo.get("corridor_box"):
    buffer_km = proportional_corridor_buffer(segment_total_km)
    route_points = geo.get("_route_decoded", [])
    if route_points:
        prop_box = corridor_bbox(route_points, 0, segment_total_km, buffer_km=buffer_km)
        is_inside = (
            prop_box["min_lat"] <= coords[0] <= prop_box["max_lat"]
            and prop_box["min_lon"] <= coords[1] <= prop_box["max_lon"]
        )
        if not is_inside:
            opt["outside_corridor"] = True
            opt["corridor_distance_km"] = _min_distance_to_bbox(coords, prop_box)
            # D-04: FLAG but do NOT reject
            await debug_logger.log(
                LogLevel.INFO,
                f"  Ausserhalb Korridor ({opt['corridor_distance_km']:.0f} km): {place}",
                job_id=job_id, agent="StopOptionsFinder",
            )
```

### Example 3: Bearing Check

```python
# In _enrich_one(), after corridor check:

# Bearing check: detect backtracking (D-09)
if prev_coords and target_coords and not geo.get("rundreise_mode", False):
    d_prev_to_stop = _haversine_km(prev_coords, coords)
    if d_prev_to_stop > 20:  # Skip for very short distances
        route_bearing = bearing_degrees(prev_coords, target_coords)
        stop_bearing = bearing_degrees(prev_coords, coords)
        deviation = bearing_deviation(route_bearing, stop_bearing)
        if deviation > 90:  # Configurable threshold
            await debug_logger.log(
                LogLevel.DEBUG,
                f"  Verworfen (Backtracking: {deviation:.0f} Abweichung): {place}",
                job_id=job_id, agent="StopOptionsFinder",
            )
            return None  # Reject -- will trigger re-ask
```

### Example 4: Frontend Corridor Warning Badge

```javascript
// In route-builder.js, inside the card rendering function:
// Add after existing badge rendering, using esc() for user content:

if (opt.outside_corridor) {
  const distText = esc(String(opt.corridor_distance_km || '?'));
  const badge = document.createElement('span');
  badge.className = 'badge badge-warning';
  badge.title = 'Ausserhalb des empfohlenen Routenkorridors (' + distText + ' km)';
  badge.textContent = 'Abseits der Route';
  badgeContainer.appendChild(badge);
}
```

### Example 5: SSE Plausibility Warning Handler

```javascript
// In route-builder.js openRouteSSE(), add to event handlers:

style_mismatch_warning: data => {
  const warning = data.warning || '';
  const suggestions = (data.suggestions || []).join(', ');
  const banner = document.createElement('div');
  banner.className = 'plausibility-banner';

  const iconEl = document.createElement('div');
  iconEl.className = 'plausibility-icon';
  iconEl.textContent = '\u26A0';
  banner.appendChild(iconEl);

  const textEl = document.createElement('div');
  textEl.className = 'plausibility-text';
  const strong = document.createElement('strong');
  strong.textContent = 'Hinweis';
  textEl.appendChild(strong);
  const p = document.createElement('p');
  p.textContent = warning;
  textEl.appendChild(p);
  if (suggestions) {
    const p2 = document.createElement('p');
    p2.textContent = 'Alternativen: ' + suggestions;
    textEl.appendChild(p2);
  }
  banner.appendChild(textEl);

  const btn = document.createElement('button');
  btn.textContent = 'Trotzdem weiter';
  btn.addEventListener('click', () => banner.remove());
  const actions = document.createElement('div');
  actions.className = 'plausibility-actions';
  actions.appendChild(btn);
  banner.appendChild(actions);

  const panel = document.getElementById('route-builder-panel');
  if (panel && panel.firstChild) {
    panel.insertBefore(banner, panel.firstChild);
  }
},
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 + pytest-mock 3.15.1 + pytest-asyncio 1.2.0 |
| Config file | None (convention-based, `backend/tests/`) |
| Quick run command | `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -x -q` |
| Full suite command | `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AIQ-01 | StopOptionsFinder uses `claude-sonnet-4-5` as prod model | unit | `pytest tests/test_agents_mock.py::test_stop_options_finder_prod_model -x` | Wave 0 |
| AIQ-02 | Corridor validation flags outside-corridor stops | unit | `pytest tests/test_validation.py::test_corridor_flag -x` | Wave 0 |
| AIQ-02 | Proportional corridor width calculation | unit | `pytest tests/test_validation.py::test_proportional_corridor_buffer -x` | Wave 0 |
| AIQ-03 | Travel style included in StopOptionsFinder prompt | unit | `pytest tests/test_agents_mock.py::test_stop_options_style_enforcement -x` | Wave 0 |
| AIQ-04 | Quality validation rejects low-quality stops | unit | `pytest tests/test_validation.py::test_quality_validation_reject -x` | Wave 0 |
| AIQ-04 | Silent re-ask produces replacement | unit | `pytest tests/test_validation.py::test_silent_reask -x` | Wave 0 |
| AIQ-05 | Bearing calculation correctness | unit | `pytest tests/test_validation.py::test_bearing_degrees -x` | Wave 0 |
| AIQ-05 | Backtracking detection rejects zigzag stops | unit | `pytest tests/test_validation.py::test_backtracking_detection -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -x -q`
- **Per wave merge:** `cd /Users/stefan/Code/Travelman3/backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_validation.py` -- new file for corridor, bearing, quality validation unit tests
- [ ] Tests for `bearing_degrees()` and `bearing_deviation()` math correctness
- [ ] Tests for `proportional_corridor_buffer()` clamping behavior
- [ ] Tests for Google Places quality validation (mocked)
- [ ] Test for StopOptionsFinder production model assignment in `test_agents_mock.py`

## Open Questions

1. **Plausibility challenge timeout mechanism**
   - What we know: The frontend receives `style_mismatch_warning` SSE event. User can dismiss or adjust.
   - What's unclear: How does the backend know to proceed? Options: (a) backend always proceeds after emitting the warning (fire-and-forget), (b) backend waits for an HTTP endpoint call to confirm/adjust, with a timeout.
   - Recommendation: Fire-and-forget approach (a). The warning is informational. RouteArchitect proceeds immediately with best-available route. If user adjusts styles, they re-submit the form. This avoids timeout complexity and job-stalling risk.

2. **Quality validation API cost per job**
   - What we know: `find_place_from_text()` costs $17/1000 calls. A 10-day trip with ~5 stops x 3 options x up to 2 retries = ~30 calls = ~$0.51.
   - What's unclear: Whether `nearby_search()` ($32/1000) is needed in addition, or if `find_place_from_text()` alone is sufficient.
   - Recommendation: Start with `find_place_from_text()` only. Add `nearby_search()` in a later phase if quality is still insufficient. This keeps costs at ~$0.51 per trip.

3. **Corridor check interaction with Rundreise mode**
   - What we know: Rundreise mode (circular route) explicitly encourages detours. Corridor checks would reject most stops.
   - What's unclear: Confirmed in code -- `geo.get("rundreise_mode", False)` is already checked.
   - Recommendation: Skip corridor AND bearing checks when `rundreise_mode` is True. This is already the pattern for the overshoot check.

## Sources

### Primary (HIGH confidence)
- `backend/agents/stop_options_finder.py` -- bug confirmed at line 33: `get_model("claude-haiku-4-5", AGENT_KEY)` should be `"claude-sonnet-4-5"`
- `backend/agents/_client.py` -- `get_model()` function confirms TEST_MODE handling is correct, only the prod_model argument is wrong
- `backend/main.py:680-930` -- existing `_find_and_stream_options()` provides the validation insertion points
- `backend/utils/maps_helper.py` -- `corridor_bbox()`, `haversine_km()`, `decode_polyline5()` already implement needed geo utilities
- `backend/utils/google_places.py` -- `find_place_from_text()`, `nearby_search()` already available for quality validation
- `backend/models/stop_option.py` -- current StopOption model needs 2-3 new optional fields
- `frontend/js/route-builder.js` -- SSE handler pattern at line 18 shows how to add new event types

### Secondary (MEDIUM confidence)
- Bearing calculation formula -- standard initial bearing formula from aviation/navigation (well-established math)
- Proportional corridor width -- 20% with [15, 100] km clamps is a reasonable starting point, may need tuning

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all tools already in codebase
- Architecture: HIGH -- clear insertion points identified in existing code, patterns well-established
- Pitfalls: HIGH -- based on direct code analysis of existing validation pipeline

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no external dependency changes expected)
