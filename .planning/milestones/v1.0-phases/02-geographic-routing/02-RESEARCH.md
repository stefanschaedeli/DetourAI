# Phase 02: Geographic Routing - Research

**Researched:** 2026-03-25
**Domain:** Ferry-aware geographic routing, Google Directions fallback, island coordinate validation
**Confidence:** HIGH

## Summary

Phase 2 extends the existing route planning pipeline with ferry awareness for island and coastal destinations. The core challenge is that Google Directions API returns `(0.0, 0.0, "")` (the existing failure sentinel) when no driving route exists across water -- this is the primary detection point for ferry crossings. The system must construct haversine-based ferry estimates as fallback, validate island coordinates against actual island locations, and deduct ferry time from daily driving budgets.

The codebase is well-prepared for this phase. The route architect already returns a `ferry_crossings: []` field, the output generator already has `ferries_chf` in cost breakdowns, and `haversine_km()` is available in `maps_helper.py`. The main work involves: (1) a lightweight island/port lookup table, (2) ferry detection logic when `google_directions()` returns zeros, (3) prompt updates to route architect and day planner for ferry awareness, (4) corridor validation bypass for island destinations, and (5) ferry time deduction in day planning.

**Primary recommendation:** Build ferry detection as a utility function in `maps_helper.py` that wraps `google_directions()` -- when it returns `(0.0, 0.0, "")`, check the island lookup table, and return a ferry estimate instead. This keeps the change surgical: callers that already handle the `(0.0, 0.0, "")` case get ferry awareness automatically.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Detect water crossings via haversine vs driving distance divergence. When Google Directions returns `(0.0, 0.0, "")`, or driving distance is implausibly longer than haversine, infer a ferry crossing.
- D-02: Route architect prompt explicitly instructs Claude to identify ferry segments when planning routes to/through island destinations.
- D-03: Ferry crossings appear as dedicated ferry legs in the route -- distinct from driving legs. SSE events include a ferry indicator and estimated crossing time.
- D-04: Primary ferry port identification is done by the route architect agent (claude-opus-4-5). A lightweight lookup table provides validation hints.
- D-05: Island group coverage: Common Mediterranean -- Greek islands (Cyclades, Dodecanese, Ionian), Corsica, Sardinia, Sicily, Balearics, Croatian islands.
- D-06: Lookup table maps island groups to primary ferry ports (e.g., Cyclades -> Piraeus, Corsica -> Nice/Marseille/Livorno).
- D-07: When Google Directions returns no route for a water crossing, construct a haversine-based ferry estimate. Estimated ferry speed: ~30 km/h average. Segment flagged as `is_ferry: true`.
- D-08: No retry with different waypoints -- use ferry estimate directly.
- D-09: Stop finder coordinate validation extended: when destination is an island, corridor check must use island's actual bounding box, not land-based corridor from mainland.
- D-10: When geocoding island destinations, validate coordinates fall on the island (not nearby mainland). Use haversine from island center as sanity check.
- D-11: Ferry crossing time deducted from daily max_drive_hours. 3h ferry on 4.5h/day budget leaves 1.5h driving.
- D-12: Ferry cost tracked as separate budget line (`ferries_chf`). Claude estimates cost based on route, vehicle type, passenger count.

### Claude's Discretion
- Exact haversine/driving distance divergence threshold for ferry detection
- Ferry speed estimate (30 km/h suggested, can tune)
- Lookup table format and data structure (dict, JSON file, or inline)
- How many ferry port alternatives to include per island group
- Exact wording of German-language ferry-related SSE messages
- Whether to show ferry duration as a range or point estimate

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEO-01 | Route planning handles island destinations by identifying ferry crossings and port cities | Route architect prompt update + island lookup table for port validation (D-02, D-04, D-06) |
| GEO-02 | Stop finder resolves coordinates to actual island locations, not nearby mainland points | Geocode validation with island center haversine check + island bounding boxes (D-09, D-10) |
| GEO-03 | System detects when Google Directions returns no route and attempts ferry-aware alternatives | `google_directions()` returns `(0.0, 0.0, "")` -- wrap with ferry fallback using haversine estimate (D-01, D-07, D-08) |
| GEO-04 | Common island groups have ferry-port awareness | Lookup table covering Mediterranean island groups with primary ports (D-05, D-06) |
| GEO-05 | Route planning accounts for ferry time in daily driving budget | DayPlanner prompt update + `_fallback_cost_estimate()` ferry cost integration (D-11, D-12) |
</phase_requirements>

## Architecture Patterns

### Integration Points Map

The ferry awareness system touches these existing components:

```
backend/
  utils/
    maps_helper.py           # ADD: ferry_estimate(), is_island_destination(), ISLAND_FERRY_PORTS
    ferry_ports.py            # NEW: island/port lookup table data + helper functions
  agents/
    route_architect.py        # MODIFY: prompt to identify ferry segments
    stop_options_finder.py    # MODIFY: corridor check bypass for island destinations
    day_planner.py            # MODIFY: prompt + _fallback_cost_estimate() for ferry time/cost
    region_planner.py         # MODIFY: prompt for island region awareness
  models/
    travel_response.py        # ADD: is_ferry field on TravelStop or new FerryLeg concept
    stop_option.py            # ADD: is_ferry_required field
  main.py                     # MODIFY: route enrichment to use ferry fallback
  tests/
    test_ferry.py             # NEW: ferry detection, estimation, island validation tests
```

### Pattern 1: Ferry-Aware Directions Wrapper

**What:** A wrapper function around `google_directions()` that falls back to haversine-based ferry estimation when no driving route exists.
**When to use:** Every place where `google_directions()` or `google_directions_simple()` is called and the result might cross water.

```python
# Source: Derived from existing maps_helper.py patterns
FERRY_SPEED_KMH = 30.0  # Average ferry speed (D-07)

async def google_directions_with_ferry(
    origin: str, destination: str, waypoints: list[str] = None
) -> tuple[float, float, str, bool]:
    """Like google_directions() but returns (hours, km, polyline, is_ferry).
    When Google returns no route, checks island lookup and constructs ferry estimate."""
    hours, km, polyline = await google_directions(origin, destination, waypoints)
    if hours > 0 and km > 0:
        return (hours, km, polyline, False)

    # Google returned no route -- check if this is a water crossing
    origin_geo = await geocode_google(origin)
    dest_geo = await geocode_google(destination)
    if not origin_geo or not dest_geo:
        return (0.0, 0.0, "", False)

    origin_coords = (origin_geo[0], origin_geo[1])
    dest_coords = (dest_geo[0], dest_geo[1])
    straight_km = haversine_km(origin_coords, dest_coords)

    # If either endpoint is in an island group, assume ferry
    if is_island_destination(dest_coords) or is_island_destination(origin_coords):
        ferry_hours = round(straight_km / FERRY_SPEED_KMH, 1)
        return (ferry_hours, round(straight_km, 0), "", True)

    return (0.0, 0.0, "", False)
```

### Pattern 2: Island/Port Lookup Table

**What:** A Python dict mapping island group names to bounding boxes and primary ferry ports.
**When to use:** Validation of AI suggestions, ferry port identification, island coordinate checks.

```python
# Source: Research-compiled Mediterranean ferry data
# Recommended: backend/utils/ferry_ports.py

ISLAND_GROUPS: dict[str, dict] = {
    "cyclades": {
        "bbox": {"min_lat": 36.3, "max_lat": 37.7, "min_lon": 24.4, "max_lon": 26.3},
        "center": (37.0, 25.4),
        "primary_ports": ["Piraeus", "Rafina"],
        "ferry_hours_range": (4, 9),  # typical crossing time range
    },
    "dodecanese": {
        "bbox": {"min_lat": 35.9, "max_lat": 37.2, "min_lon": 26.7, "max_lon": 28.3},
        "center": (36.4, 27.9),
        "primary_ports": ["Piraeus", "Rafina"],
        "ferry_hours_range": (8, 18),
    },
    "ionian": {
        "bbox": {"min_lat": 38.6, "max_lat": 39.8, "min_lon": 19.6, "max_lon": 20.8},
        "center": (39.6, 19.9),
        "primary_ports": ["Igoumenitsa", "Patras"],
        "ferry_hours_range": (1, 3),
    },
    "corsica": {
        "bbox": {"min_lat": 41.4, "max_lat": 43.0, "min_lon": 8.5, "max_lon": 9.6},
        "center": (42.15, 9.1),
        "primary_ports": ["Nice", "Marseille", "Livorno", "Genua"],
        "ferry_hours_range": (4, 12),
    },
    "sardinia": {
        "bbox": {"min_lat": 38.8, "max_lat": 41.3, "min_lon": 8.1, "max_lon": 9.8},
        "center": (40.0, 9.0),
        "primary_ports": ["Civitavecchia", "Livorno", "Genua", "Bonifacio"],
        "ferry_hours_range": (5, 12),
    },
    "sicily": {
        "bbox": {"min_lat": 36.6, "max_lat": 38.3, "min_lon": 12.4, "max_lon": 15.7},
        "center": (37.5, 14.0),
        "primary_ports": ["Villa San Giovanni", "Salerno", "Napoli"],
        "ferry_hours_range": (0.3, 10),  # Messina strait = 20min, from Naples = 10h
    },
    "balearics": {
        "bbox": {"min_lat": 38.6, "max_lat": 40.1, "min_lon": 1.1, "max_lon": 4.4},
        "center": (39.5, 2.9),
        "primary_ports": ["Barcelona", "Valencia", "Denia"],
        "ferry_hours_range": (4, 9),
    },
    "croatian_islands": {
        "bbox": {"min_lat": 42.4, "max_lat": 44.3, "min_lon": 14.7, "max_lon": 17.3},
        "center": (43.2, 16.4),
        "primary_ports": ["Split", "Dubrovnik", "Zadar", "Rijeka"],
        "ferry_hours_range": (0.5, 4),
    },
}
```

**Note on Sicily:** Sicily is connected to mainland Italy via the Messina Strait. Google Directions DOES return a driving route for this (via the ferry at Villa San Giovanni), so this is a case where `google_directions()` succeeds but the route includes a built-in ferry. The divergence detection (D-01) handles this: haversine ~3 km but driving ~15 km through the strait area.

### Pattern 3: Island Coordinate Validation

**What:** Check if geocoded coordinates fall within an island bounding box.
**When to use:** After `geocode_google()` for island destinations in the stop finder.

```python
def is_island_destination(coords: tuple[float, float]) -> Optional[str]:
    """Returns island group name if coords fall within a known island bbox, else None."""
    lat, lon = coords
    for group_name, group in ISLAND_GROUPS.items():
        bbox = group["bbox"]
        if (bbox["min_lat"] <= lat <= bbox["max_lat"] and
            bbox["min_lon"] <= lon <= bbox["max_lon"]):
            return group_name
    return None

def validate_island_coordinates(
    place_name: str, coords: tuple[float, float], expected_island_group: str
) -> bool:
    """Verify geocoded coords are on the expected island, not nearby mainland."""
    group = ISLAND_GROUPS.get(expected_island_group)
    if not group:
        return True  # unknown group, can't validate
    center = group["center"]
    distance_from_center = haversine_km(coords, center)
    # If coords are within reasonable distance of island group center, accept
    # Max radius varies by island group size
    max_radius_km = max(
        haversine_km((group["bbox"]["min_lat"], group["bbox"]["min_lon"]),
                     (group["bbox"]["max_lat"], group["bbox"]["max_lon"])) / 2,
        50.0  # minimum 50km radius
    )
    return distance_from_center <= max_radius_km
```

### Pattern 4: Corridor Bypass for Island Destinations

**What:** When the segment target is on an island, skip the land-based corridor check and bearing check.
**When to use:** In `_find_and_stream_options()` in `main.py` (lines ~847-888).

The corridor check and bearing check assume a continuous land route. For ferry routes, stops before the ferry (e.g., Athens, Piraeus) won't be "between" the origin and an island destination on a land corridor. The validation must recognize this:

```python
# In _find_and_stream_options._enrich_one():
# Before corridor check, detect if we're routing to an island
target_island = is_island_destination(target_coords) if target_coords else None
if target_island:
    # Skip land-based corridor check for island destinations
    # Stops leading to a ferry port are valid even if off the "direct" corridor
    pass
else:
    # existing corridor check logic
    ...
```

### Anti-Patterns to Avoid

- **Calling external ferry APIs:** No real-time ferry schedule APIs. Use AI estimation + haversine fallback. The user explicitly decided against external API calls (D-08).
- **Retrying Google Directions with transit mode:** The `mode: "transit"` parameter covers public transit, not car ferries. It would return bus/train routes, not ferry options.
- **Hardcoding ferry durations:** Use the lookup table's `ferry_hours_range` for validation, but let Claude estimate based on context. Haversine / 30 km/h is the formula for the fallback.
- **Treating Sicily as always-ferry:** Google Directions returns driving routes through the Messina Strait ferry. Only flag it via divergence detection, don't force ferry mode.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Haversine distance | Custom math | `haversine_km()` from `maps_helper.py` | Already exists, tested |
| Ferry schedule lookup | Real-time API integration | AI estimation + static lookup table | No reliable free API, user decision D-08 |
| Polyline decoding | Custom decoder | `decode_polyline5()` from `maps_helper.py` | Already exists |
| Route corridor check | New corridor system | Extend existing `corridor_bbox()` + `proportional_corridor_buffer()` | Phase 1 already built this |
| JSON parsing from agents | Custom parser | `parse_agent_json()` from `json_parser.py` | Handles markdown fences, truncation |

## Common Pitfalls

### Pitfall 1: Google Directions Sometimes Includes Ferries
**What goes wrong:** Assuming `google_directions()` always returns `(0.0, 0.0, "")` for water crossings. In reality, Google sometimes includes ferry segments in driving routes (e.g., Messina Strait, some short Norwegian fjord crossings).
**Why it happens:** Google's driving mode can route through car ferry terminals when the ferry is considered part of the road network.
**How to avoid:** Implement BOTH detection paths: (1) `(0.0, 0.0, "")` for no-route cases, and (2) haversine-vs-driving divergence for routes that implicitly include ferries.
**Warning signs:** Routes that show implausibly high driving time relative to haversine distance.

### Pitfall 2: Geocoding Island Names to Mainland
**What goes wrong:** `geocode_google("Santorini")` could potentially return coordinates near the Athens mainland if Google's geocoder is ambiguous.
**Why it happens:** Google geocoder prioritizes populated areas; some island names match mainland locations.
**How to avoid:** After geocoding, verify coordinates fall within the expected island bounding box. If they don't, re-geocode with country code hint (e.g., "Santorini, GR").
**Warning signs:** Island destination coordinates that are on the mainland side of the coast.

### Pitfall 3: Ferry Time Not Deducted from Driving Budget
**What goes wrong:** A day with a 5-hour ferry crossing and 4.5h max driving budget gets planned with 4.5h of additional driving.
**Why it happens:** DayPlanner doesn't know about ferry time unless explicitly told.
**How to avoid:** Pass ferry segment data to DayPlanner. In the prompt, explicitly state: "Dieser Tag beinhaltet eine Faehrueberfahrt von X Stunden. Verbleibende Fahrzeit: Y Stunden."
**Warning signs:** Day plans where total transport time (ferry + driving) exceeds max_drive_hours.

### Pitfall 4: Corridor Check Rejects Valid Pre-Ferry Stops
**What goes wrong:** Stops near ferry ports (e.g., Athens/Piraeus for Cyclades trips) get rejected because they're "outside the corridor" from a mainland-only perspective.
**Why it happens:** The corridor is computed from `google_directions()` polyline, which doesn't exist for water crossings.
**How to avoid:** Detect island destinations early and bypass or widen the corridor check. Pre-ferry port stops are valid regardless of corridor position.
**Warning signs:** All stop options getting filtered out for island-destination legs.

### Pitfall 5: Bounding Box Overlap Between Island Groups
**What goes wrong:** Some coordinates might match multiple island groups, or narrow strait areas could be ambiguous.
**Why it happens:** Island groups have geographically close bounding boxes (e.g., Dodecanese and parts of mainland Turkey).
**How to avoid:** Order matching from most specific to least specific. Use the `is_island_destination()` function that returns the first match, and ensure bounding boxes don't overlap excessively.
**Warning signs:** Mainland coastal cities being identified as "island" destinations.

## Code Examples

### Example 1: Ferry Detection in Route Enrichment

The main integration point is in `main.py` route enrichment loop. Currently `google_directions_simple()` is called and `(0.0, 0.0)` is treated as failure:

```python
# Current pattern in day_planner.py _enrich_with_google():
hours, km = await google_directions_simple(locations[i - 1], locations[i])
# When hours=0, km=0 -- currently just uses fallback

# New pattern:
hours, km, _, is_ferry = await google_directions_with_ferry(locations[i - 1], locations[i])
if is_ferry:
    s["is_ferry"] = True
    s["ferry_hours"] = hours
    s["ferry_km"] = km
```

### Example 2: Route Architect Prompt Addition

```python
# Addition to route_architect.py prompt (after existing content):
ferry_block = ""
# Detect if destination might be an island
dest_geo = await geocode_google(req.main_destination)
if dest_geo:
    island_group = is_island_destination((dest_geo[0], dest_geo[1]))
    if island_group:
        ports = ISLAND_GROUPS[island_group].get("primary_ports", [])
        ferry_block = (
            f"\nINSEL-ZIEL ERKANNT: {req.main_destination} ist eine Insel ({island_group}). "
            f"Die Route MUSS einen Faehrhafen beinhalten. "
            f"Uebliche Faehrhaefen fuer diese Region: {', '.join(ports)}. "
            f"Fuege den Faehrhafen als eigenen Stopp ein. "
            f"Trage die Faehrueberfahrt in ferry_crossings ein mit: "
            f"from_port, to_port, estimated_hours, estimated_cost_chf.\n"
        )
```

### Example 3: DayPlanner Ferry Time Deduction

```python
# In day_planner.py _plan_single_day(), when building prompt:
ferry_info = ""
if day_ctx.get("is_ferry"):
    ferry_hours = day_ctx.get("ferry_hours", 0)
    remaining_drive = max(0, self.request.max_drive_hours_per_day - ferry_hours)
    ferry_info = (
        f"\nFAEHRE: Dieser Tag beinhaltet eine Faehrueberfahrt von {ferry_hours:.1f} Stunden. "
        f"Verbleibende Fahrzeit nach der Faehre: {remaining_drive:.1f}h. "
        f"Plane die Faehre als eigenen time_block mit activity_type 'ferry' ein.\n"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Google Directions API | Routes API (successor) | March 2025 | Legacy Directions API still works, project uses it. Migration not needed for this phase. |
| No ferry awareness | Haversine fallback + AI identification | This phase | Routes to islands now complete instead of failing |

**Note on Google Routes API:** Google deprecated the Directions API to "Legacy" status in March 2025 and replaced it with the Routes API. However, the Legacy API still functions and the project uses it via REST. Migration to Routes API is NOT in scope for this phase -- it would be a separate infrastructure change. The ferry detection approach works identically with either API since both return the same no-route behavior for water crossings.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | None (uses default discovery) |
| Quick run command | `cd backend && python3 -m pytest tests/test_ferry.py -v` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEO-01 | Route architect identifies ferry crossings for island destinations | unit (mock) | `pytest tests/test_ferry.py::test_route_architect_ferry_prompt -x` | Wave 0 |
| GEO-02 | Island coordinates validated against bounding boxes | unit | `pytest tests/test_ferry.py::test_island_coordinate_validation -x` | Wave 0 |
| GEO-03 | Ferry fallback when google_directions returns (0,0,"") | unit | `pytest tests/test_ferry.py::test_ferry_fallback_on_zero_result -x` | Wave 0 |
| GEO-04 | Island groups have ferry port data | unit | `pytest tests/test_ferry.py::test_island_groups_coverage -x` | Wave 0 |
| GEO-05 | Ferry time deducted from daily driving budget | unit | `pytest tests/test_ferry.py::test_ferry_time_deduction -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_ferry.py -v`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ferry.py` -- covers GEO-01 through GEO-05
- [ ] Ferry utility functions need no additional conftest fixtures beyond existing ones

## Open Questions

1. **Haversine/driving divergence threshold for implicit ferry detection (D-01)**
   - What we know: Google sometimes includes ferries in driving routes (e.g., Messina Strait). The driving distance will be much larger than haversine for these cases.
   - What's unclear: Exact threshold ratio. A 2x ratio (driving / haversine > 2.0) might work, but coastal routes can also have high ratios due to winding roads.
   - Recommendation: Start with ratio > 3.0 as a conservative threshold. This catches obvious ferry inclusions (Messina: ~3km haversine, ~15km driving) while avoiding false positives on coastal roads. Tunable via the lookup table.

2. **Ferry cost estimation accuracy**
   - What we know: D-12 says Claude estimates ferry cost. Real ferry prices vary enormously (EUR 30-300+ per vehicle depending on route, season, vehicle).
   - What's unclear: How accurate Claude's estimates will be for specific routes.
   - Recommendation: For the fallback cost estimate in `_fallback_cost_estimate()`, use a rough formula: EUR 50 + (ferry_km * 0.5) per vehicle, converted to CHF. Let Claude override with more specific estimates in the prompt.

3. **Google Directions behavior for specific island routes**
   - What we know: Island destinations without bridge connections likely return ZERO_RESULTS in driving mode.
   - What's unclear: Exact behavior for all covered island groups -- some short crossings (Croatian islands) might have ferry included in driving results.
   - Recommendation: The dual detection approach (ZERO_RESULTS + divergence ratio) handles both cases. Validate with real API calls during implementation if TEST_MODE allows.

## Project Constraints (from CLAUDE.md)

- All user-facing text in German (SSE messages, error messages)
- Prices always in CHF
- Agents return valid JSON only
- All Claude calls go through `call_with_retry()`
- Agent JSON parsed via `parse_agent_json()`
- Log every API call with `debug_logger.log(LogLevel.API, ...)` before calling
- New components must be added to `_COMPONENT_MAP` in `debug_logger.py`
- Type hints on all function signatures
- Pydantic models for all API boundaries
- `async/await` throughout; blocking SDK calls wrapped in `asyncio.to_thread()`
- Git: commit immediately after every change, tag with patch version, push

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `backend/utils/maps_helper.py` -- all existing geo utility functions
- Codebase analysis: `backend/agents/route_architect.py` -- existing `ferry_crossings: []` field in prompt
- Codebase analysis: `backend/agents/day_planner.py` -- existing `_fallback_cost_estimate()` with `ferries_chf: 0.0`
- Codebase analysis: `backend/models/travel_response.py` -- existing `CostEstimate.ferries_chf` field
- Codebase analysis: `backend/main.py` lines 467-950 -- route geometry, corridor validation, enrichment

### Secondary (MEDIUM confidence)
- [Google Directions API Legacy docs](https://developers.google.com/maps/documentation/directions/get-directions) -- driving mode ferry behavior, ZERO_RESULTS status
- [Google Routes API announcement](https://mapsplatform.google.com/resources/blog/announcing-routes-api-new-enhanced-version-directions-and-distance-matrix-apis/) -- Legacy API still functional
- [Google Maps avoid ferries parameter](https://developers.google.com/maps/documentation/directions/get-directions) -- ferry is avoidable, not a separate mode

### Tertiary (LOW confidence)
- Island group bounding box coordinates -- compiled from general geographic knowledge, should be validated against actual geocoding results during implementation
- Ferry speed estimate of 30 km/h -- reasonable average for Mediterranean car ferries, but actual speeds range 15-45 km/h depending on vessel type

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries needed, extends existing codebase
- Architecture: HIGH -- integration points clearly identified from codebase analysis
- Pitfalls: HIGH -- derived from understanding actual Google Directions behavior + existing code
- Island data: MEDIUM -- bounding boxes are approximate, need validation

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no fast-moving dependencies)
