# Project Research Summary

**Project:** Travelman3 — AI Road Trip Planner
**Domain:** AI-powered road trip planning app — stabilization and UX redesign
**Researched:** 2026-03-25
**Confidence:** HIGH

## Executive Summary

Travelman3 is a working full-stack AI trip planner that needs quality stabilization before UX expansion. The core infrastructure (FastAPI, Redis, Celery, 9 AI agents, Google Maps, SQLite) is mature and should not be replaced — research confirms the existing stack is the right stack. The product has three critical quality problems that degrade the user experience regardless of how polished the UI becomes: AI stops land on the wrong continent due to missing coordinate validation, a production agent silently runs on the cheapest model (Haiku instead of Sonnet), and travel style preferences are ignored because they are buried too low in prompts. These must be fixed first.

The UX redesign direction is clear and well-supported by competitive research: every major competitor (Wanderlog, Furkot, Roadtrippers, Google Travel) places the map as the hero element with a split-panel layout. The current desktop-only, map-secondary layout is the largest gap relative to the market. The existing interactive route-building flow (pick from 3 stops per leg) is a genuine differentiator that no competitor replicates — it should be polished, not replaced. PDF/PPTX export should be removed and replaced with shareable web links, which are more valuable and require less maintenance.

The biggest implementation risk is the responsive redesign: the current UI generates HTML via 68 `innerHTML` string concatenations with desktop layout assumptions baked in. Retrofitting media queries on top of this creates a fragile mess. The architecture research strongly recommends a CSS Grid redesign from scratch with mobile-first as the foundation. The second major risk is adding stop editing controls before the Redis job state has proper locking — concurrent edits on a mutable JSON blob without versioning will corrupt state. State machine tests must be written before any edit feature is implemented.

---

## Key Findings

### Recommended Stack

The existing stack requires no replacement. Research focused on targeted additions for three new capability areas. For geographic/ferry routing, the Google Routes API v2 should replace the deprecated legacy Directions API (deprecated March 2025), and ferry awareness is primarily a prompt engineering problem — not an API problem. Google's driving mode already includes ferries when available; the gap is that agents lack geographic context about island destinations. Two optional Python libraries (`polyline 2.0.2`, `shapely 2.0.7`) can improve coordinate validation but are not required.

For the responsive UI redesign, no new libraries are needed. CSS Grid with Container Queries (`@container`), IntersectionObserver for scroll-driven map sync, and native touch events cover all requirements. For shareable links, Python's `secrets.token_urlsafe(16)` and a single new `shares` table in the existing SQLite database are sufficient — no external dependencies.

**Core technologies (new additions only):**
- Google Routes API v2: Replace legacy Directions API — same auth, better pricing, ferry step detection
- `polyline 2.0.2` (Python): Battle-tested polyline decoding — replaces hand-rolled `decode_polyline5()`
- `shapely 2.0.7` (Python): Geographic geometry operations — point-in-corridor validation
- CSS Container Queries: Responsive component layouts — native browser support since 2023, no library
- `secrets.token_urlsafe(16)` (Python stdlib): Cryptographically secure share tokens — no dependency

**Explicitly rejected:** MapLibre GL JS, Mapbox GL JS, WebSockets for route editing, Tailwind CSS, JWT-based share tokens, nanoid, booking integrations.

See `/Users/stefan/Code/Travelman3/.planning/research/STACK.md` for full rationale.

### Expected Features

The competitive landscape is definitive: map-centric layout and mobile responsiveness are table stakes that the app currently lacks. The interactive stop-picking flow is a real differentiator. PDF/PPTX export is an anti-feature.

**Must have (table stakes):**
- Map as hero element in split-panel layout — every competitor does this; current app feels outdated without it
- Mobile-responsive design — 60%+ of travel research happens on mobile; current app is desktop-only
- Consistent AI output quality — hallucinations are the #1 trust killer (CNBC March 2026); current app has known quality bugs
- Photo-rich stop cards — text-heavy lists with small images feel outdated vs. Airbnb/Google Travel
- Stop add/remove/reorder — basic CRUD on stops; Furkot and Wanderlog both offer this

**Should have (competitive differentiators):**
- Shareable trip links (public, read-only) — replaces PDF/PPTX with something superior; no competitor does this cleanly for road trips
- Interactive route building (polish existing) — already unique; improve card design and map highlighting
- Day-by-day vertical timeline — more structured than competitors' flat lists
- Budget overview dashboard — surface existing budget data visually
- Weather integration — utility already exists in `weather.py`; needs UI exposure

**Defer to v2+:**
- Mid-trip preference adjustment — high complexity (re-run affected agents), existing stop replacement covers 80% of need
- Stop quality scoring (internal) — valuable for monitoring but not user-facing; build after quality is stabilized
- Drag-and-drop reordering — desirable but lower priority than add/remove
- Real-time collaborative editing — explicitly out of scope for friends-and-family audience

**Explicit anti-features (do not build):**
PDF/PPTX export, social OAuth login, native mobile app, booking integrations, gamification, AI chat interface.

See `/Users/stefan/Code/Travelman3/.planning/research/FEATURES.md` for full analysis.

### Architecture Approach

All four new capability areas can be implemented with targeted, bounded changes to the existing architecture. No major new components are needed. Geographic awareness is pure prompt engineering plus a `_detect_water_crossing()` function in `main.py`. Route editing requires 4 new REST endpoints and `route-builder.js` enhancements. Shareable links require a schema addition to `travel_db.py` and 2 new endpoints. The responsive layout redesign is the largest change — it touches every frontend file but has zero backend impact.

**Major components and their roles in the redesign:**
1. `main.py` (2614 lines) — receives 4 new route-editing endpoints + 2 share endpoints; refactoring into FastAPI routers is technical debt worth addressing
2. `maps.js` — merge `_routeMap` and `_guideMap` into a single persistent map instance; all views share one map
3. `route-builder.js`, `accommodation.js`, `guide.js` — all render into a shared content panel; all update the single shared map
4. `travel_db.py` — add `share_token` and `is_shared` columns; add `get_by_share_token()` function
5. `stop_options_finder.py` + `route_architect.py` — prompt enrichment with geographic context; ferry port lookup injection

**Key pattern:** Route editing uses synchronous REST calls (not SSE). SSE stays reserved for long-running operations (option finding, full planning). This is architecturally correct and must not be changed.

See `/Users/stefan/Code/Travelman3/.planning/research/ARCHITECTURE.md` for full diagrams.

### Critical Pitfalls

1. **Wrong model on StopOptionsFinderAgent (existing bug)** — `stop_options_finder.py:33` hardcodes `claude-haiku-4-5` in production; must be changed to `claude-sonnet-4-5` as the very first change in the project. One-line fix that unblocks all AI quality work.

2. **LLM geographic hallucination without coordinate validation** — Claude names stops that Google Geocoding resolves to wrong locations; `corridor_bbox()` exists in `maps_helper.py` but is not used for validation. Add `validate_stop_geography()` that rejects stops > 100km from the route polyline and re-prompts. This is the root cause of the island/mainland bug.

3. **Ferry routing failure for island destinations** — `google_directions()` returns `ZERO_RESULTS` for water crossings with no fallback. Add island detection (reverse geocode check), a ferry port lookup for major destinations (Piraeus, Civitavecchia, etc.), and synthetic ferry segment construction when directions fail.

4. **Stop editing creates state machine corruption** — the Redis job state is a mutable JSON blob with no locking. Adding edit operations before writing state machine tests will cause cascading inconsistencies (stale accommodations after stop replacement, budget totals not updating). Write tests first, then add `cascade_invalidation(stop_id)` logic.

5. **Responsive redesign breaks desktop** — 68 `innerHTML` sites with desktop layout assumptions cannot be made responsive by adding media queries. Must redesign from CSS Grid foundation, mobile-first. Test at all four breakpoints (375px, 768px, 1024px, 1440px).

6. **Share links leaking private data** — dedicated stripped-down response model required for shared views; the authenticated `/api/travels/{id}` response model must never be reused. Use 22+ character crypto-random tokens, not sequential IDs or short strings.

7. **Travel style prompt dilution** — travel style preferences are buried among geographic and logistic constraints; Claude prioritizes constraints over preferences. Elevate style to CRITICAL status in system prompt with negative examples.

See `/Users/stefan/Code/Travelman3/.planning/research/PITFALLS.md` for full pitfall analysis including warning signs and recovery strategies.

---

## Implications for Roadmap

Based on combined research, four phases are recommended in strict dependency order.

### Phase 1: AI Quality Stabilization
**Rationale:** Wrong geography makes every downstream UI change unreliable. A beautiful responsive layout showing stops in the wrong country is worse than an ugly layout with correct stops. The model bug and prompt issues are the highest-leverage changes possible — they affect every trip generated.
**Delivers:** Reliable stop coordinates, correct travel style adherence, proper model usage, state machine test coverage
**Addresses:** Consistent AI output quality (table stakes), travel style fidelity (differentiator prerequisite)
**Avoids:** LLM geographic hallucination, ferry routing failure, wrong model bug, travel style dilution, state machine chaos
**Key tasks:**
- Fix `stop_options_finder.py:33` (one-line model fix — do this first)
- Add `validate_stop_geography()` with corridor validation
- Add island detection + ferry port lookup
- Elevate travel style to CRITICAL constraint in prompts
- Write state machine tests (prerequisite for Phase 2)
- Migrate `maps_helper.py` to Google Routes API v2 (ferry step detection)

### Phase 2: User Route Control
**Rationale:** Stop editing depends on correct geography from Phase 1 — reordering stops only makes sense if the stops are correctly placed. State machine tests from Phase 1 are a hard prerequisite before any edit features are added to avoid state corruption.
**Delivers:** Stop add, remove, reorder; manual stop insertion; preference adjustment
**Addresses:** Stop add/remove/edit (table stakes), interactive route building polish (differentiator)
**Avoids:** State machine corruption (requires Phase 1 tests first), stale downstream data (requires `cascade_invalidation`)
**Key tasks:**
- `POST /api/reorder-stops/{job_id}` with Google Directions recalculation
- `POST /api/remove-stop/{job_id}/{stop_id}` with cascade invalidation
- `POST /api/add-custom-stop/{job_id}` with geocoding
- `route-builder.js` drag-to-reorder and remove controls
- `cascade_invalidation(stop_id)` function with dependency graph

### Phase 3: Map-Centric Responsive Layout
**Rationale:** The largest frontend change. Must come after Phase 2 because the edit controls (drag handles, remove buttons, add fields) must be designed into the layout from the start — not retrofitted. Attempting responsive redesign while also modifying route-builder logic creates merge conflicts and regression nightmares.
**Delivers:** Split-panel map-centric layout, mobile responsive design, unified map instance, photo-rich stop cards, day-by-day timeline
**Addresses:** Map as hero (table stakes), mobile responsive (table stakes), photo-rich cards (table stakes), day-by-day timeline (differentiator)
**Avoids:** Responsive retrofit breaking desktop (requires CSS Grid from scratch), map duplication (requires single map instance)
**Key tasks:**
- `index.html`: Two-panel CSS Grid structure
- `styles.css`: Mobile-first rewrite (breakpoints: 375px, 768px, 1024px, 1440px)
- `maps.js`: Merge `_routeMap` + `_guideMap` into single persistent instance
- Bottom sheet pattern for mobile stop details
- IntersectionObserver scroll-driven map sync
- Budget dashboard visual component
- Weather data surface in day cards

### Phase 4: Sharing and Polish
**Rationale:** Shareable links are architecturally independent (clean boundaries, small scope) and can be executed after Phase 3 when the guide view they render is complete. Phase 3 must be done first so the shared read-only view uses the new polished layout.
**Delivers:** Public read-only shareable links, share/revoke controls, read-only guide view, removal of PDF/PPTX export
**Addresses:** Shareable trip links (differentiator), removal of PDF/PPTX anti-feature
**Avoids:** Share token security flaws, private data leakage in shared views
**Key tasks:**
- `travel_db.py`: Add `share_token`, `is_shared` columns with migration
- `POST /api/travels/{id}/share` and `DELETE /api/travels/{id}/share`
- `GET /api/shared/{token}` (no auth, stripped response model)
- `/shared/{token}` route in `router.js` with read-only guide rendering
- Remove `output_generator.py` (PDF/PPTX)
- Rate limiting on shared endpoint

### Phase Ordering Rationale

- Phase 1 before everything: wrong geography propagates through all downstream data; fixing it first means Phase 2-4 work on correct foundations
- Phase 2 before Phase 3: edit controls must be known before the layout is designed; the layout must accommodate drag handles, remove buttons, and add-stop fields from the start
- Phase 3 before Phase 4: the shared view renders the guide view; the guide view must be in its final responsive form before being exposed publicly
- The architecture research explicitly recommends this same ordering with the same rationale

### Research Flags

Phases likely needing `/gsd:research-phase` during planning:
- **Phase 1:** Ferry port lookup data (which ports serve which islands?) needs validation against actual Google Directions behavior for specific routes (Greek islands, Sardinia, Corsica, Balearics)
- **Phase 2:** Redis optimistic locking pattern (`WATCH`/`MULTI` transactions) — verify approach for the specific job state structure before implementing
- **Phase 3:** CSS Container Queries browser support for Safari on iOS — verify before relying on them for mobile layout

Phases with well-documented patterns (skip research-phase):
- **Phase 4:** Share token pattern is well-documented; `secrets.token_urlsafe(16)` + SQLite table is established pattern with clear implementation path

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Research based on official Google API docs, Python stdlib docs, direct codebase analysis. Recommendations are minimal and conservative (no new dependencies where stdlib suffices). |
| Features | MEDIUM | Based on competitive analysis of Wanderlog, Furkot, Roadtrippers, Google Travel. Competitive landscape well-covered but user validation for this specific friends-and-family audience not done. |
| Architecture | HIGH | Based on direct codebase analysis of actual files. All recommendations verified against existing code patterns. Build order derived from real dependency analysis. |
| Pitfalls | HIGH | Combines codebase analysis (bugs already identified in CONCERNS.md) with domain research (GDELT, AFAR, Varonis). The most critical pitfalls have line-number evidence in the actual code. |

**Overall confidence:** HIGH

### Gaps to Address

- **Ferry port coverage:** The ferry port lookup table approach is architecturally correct but the actual data (which ports, which islands, which ferry times) needs validation against Google Routes API behavior for specific test routes. Recommend testing Athens-Santorini, Rome-Sardinia, and Barcelona-Mallorca as the three canonical cases before finalizing the lookup table.
- **`main.py` refactoring scope:** At 2614 lines, `main.py` is flagged as technical debt. The roadmap should decide whether Phase 2 (adding 4 endpoints) is the trigger for extracting FastAPI routers, or whether this is a separate cleanup phase. Research does not prescribe timing.
- **Redis locking strategy:** `WATCH`/`MULTI` transactions are the standard Redis optimistic locking approach, but the specific implementation for the job state structure needs a spike before Phase 2 planning. Adding edit endpoints without resolving this first is the scenario that leads to state corruption.
- **Google Routes API quota/pricing:** Migrating from legacy Directions API requires enabling a separate API in GCP Console (`Routes API`). Pricing differs from legacy. Validate the quota limits against expected trip volume before migration.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — `/Users/stefan/Code/Travelman3/` (all architectural findings verified against actual code)
- [Google Routes API — computeRoutes](https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes) — verified travel modes and ferry behavior
- [Google Routes API Migration Announcement](https://mapsplatform.google.com/resources/blog/announcing-routes-api-new-enhanced-version-directions-and-distance-matrix-apis/) — confirmed March 2025 deprecation
- [Python secrets module](https://docs.python.org/3/library/secrets.html) — stdlib token generation
- [GDELT Project: LLM-Based Geocoders Struggle](https://blog.gdeltproject.org/generative-ai-experiments-why-llm-based-geocoders-struggle/) — LLM geographic hallucination evidence

### Secondary (MEDIUM confidence)
- [Wanderlog](https://wanderlog.com/), [Furkot](https://furkot.com/), [Roadtrippers](https://roadtrippers.com/) — competitive feature analysis
- [CNBC: AI travel planners growing but hallucinations persist (March 2026)](https://www.cnbc.com/2026/03/11/ai-travel-planners-tourism-popularity-trust-hallucinations.html) — market context
- [TravelTime: Interactive map design and UX examples](https://traveltime.com/blog/interactive-map-design-ux-mobile-desktop) — map-centric layout patterns
- [Varonis: The Dangers of Shared Links](https://www.varonis.com/blog/the-dangers-of-shared-links) — share token security
- [OpenRouteService ferry routing issues](https://ask.openrouteservice.org/t/route-wont-take-ferry/461) — rejection rationale for ORS

### Tertiary (LOW confidence)
- [AFAR: Common Mistakes AI Makes When Planning Travel](https://www.afar.com/magazine/the-most-common-mistakes-ai-makes-when-planning-travel) — AI travel failure modes (no direct implementation guidance)

---
*Research completed: 2026-03-25*
*Ready for roadmap: yes*
