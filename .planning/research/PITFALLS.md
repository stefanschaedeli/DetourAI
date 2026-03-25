# Pitfalls Research

**Domain:** AI-powered road trip planner -- stabilization, UX redesign, and sharing features
**Researched:** 2026-03-25
**Confidence:** HIGH (based on codebase analysis + domain research)

## Critical Pitfalls

### Pitfall 1: LLM Geographic Hallucination Without Verification

**What goes wrong:**
Claude generates stop names that sound plausible but are geographically wrong. The StopOptionsFinderAgent suggests "Mykonos Town" for a driving route, but the coordinates land on mainland Greece because Google Geocoding resolves an ambiguous name to the wrong location. The system currently has no post-geocoding validation that a stop actually lies on or near the intended route corridor. This is the root cause of the existing "stops landing on mainland instead of target islands" bug.

**Why it happens:**
LLMs are poor geocoders -- research from GDELT Project shows they miss more than half of location mentions in text, hallucinate locations, and conflate cities with unrelated places. The current architecture trusts Claude's geographic reasoning entirely: the StopOptionsFinderAgent names a place, `geocode_google()` resolves it, and the result is accepted without checking whether the resolved coordinates are within the route corridor or even in the correct country.

**How to avoid:**
1. After geocoding every AI-suggested stop, validate that coordinates fall within the expected route corridor bounding box (the `corridor_bbox()` function already exists in `maps_helper.py` but is not used for validation).
2. When the destination is an island, detect this by checking if Google Geocoding returns a `place_id` whose geometry is surrounded by water, or by maintaining a known-islands lookup for common destinations (Greek islands, Balearics, Canaries, etc.).
3. Add a `validate_stop_geography()` function that rejects stops whose geocoded position is more than X km from the route polyline, and re-prompts the agent with the rejection reason.
4. Include explicit lat/lon bounding boxes in the StopOptionsFinderAgent prompt so Claude knows the geographic constraints.

**Warning signs:**
- Stop coordinates have haversine distance > 100km from route polyline
- Stop country code doesn't match expected segment countries
- Multiple stops cluster in the same small area (duplicates from ambiguous naming)
- Google Directions returns `ZERO_RESULTS` for a leg (no drivable route exists)

**Phase to address:**
Phase 1 (AI Quality) -- this is the most impactful quality fix

---

### Pitfall 2: Google Directions API Cannot Route Through Ferries Predictably

**What goes wrong:**
When planning routes to islands (Greek islands, Sardinia, Corsica, etc.), `google_directions()` with `mode: "driving"` returns `ZERO_RESULTS` or routes through absurd detours because there is no drivable road connection. The current code treats `(0.0, 0.0, "")` as "no route found" but doesn't distinguish "no road exists" from "API error." The `reference_cities_along_route_google()` function returns an empty list, leaving the StopOptionsFinderAgent with no geographic anchors for the segment.

**Why it happens:**
Google Directions API's driving mode includes ferry routes by default (you have to explicitly `avoid=ferries` to exclude them), but coverage is inconsistent -- it knows about major car ferries (e.g., Dover-Calais) but not many Greek inter-island ferries. There is no "require ferries" option. The app has no fallback when driving directions fail for water crossings.

**How to avoid:**
1. Detect island/water-crossing segments early: if `google_directions()` returns zero results for a segment, check if the destination is an island (geocode + reverse geocode to check if locality is on an island).
2. For island segments, switch to a two-part routing strategy: mainland-to-port + port-to-island-destination, with a synthetic ferry segment in between.
3. Maintain a lookup of major ferry ports for popular island destinations (Piraeus for Greek islands, Civitavecchia for Sardinia, etc.).
4. When Directions API returns zero results, construct route geometry from straight-line distance + estimated ferry time rather than showing nothing.

**Warning signs:**
- `google_directions()` returns `(0.0, 0.0, "")` for a leg
- Route polyline has gaps or jumps across water
- Total route distance is dramatically different from straight-line distance
- The `ferry_crossings` array in RouteArchitect output is empty despite island destinations

**Phase to address:**
Phase 1 (AI Quality) -- must be solved before the route works for coastal/island trips

---

### Pitfall 3: Responsive Redesign Breaks Desktop While Fixing Mobile

**What goes wrong:**
When converting the existing desktop-optimized vanilla JS UI to responsive, developers typically start from mobile and accidentally degrade the desktop experience. The current app has 68 `innerHTML` assignments across 11 JS files, all generating desktop-assumption HTML. Making this responsive by adding CSS media queries alone leads to layouts that technically resize but feel cramped or awkward at every breakpoint. The map (hero element in redesign) either dominates mobile completely (no room for content) or shrinks to uselessness.

**Why it happens:**
The existing HTML is generated dynamically via string concatenation in JS (`innerHTML`). These strings embed layout assumptions (grid column counts, fixed widths, pixel-based spacing). Making them responsive requires changing both the JS that generates HTML and the CSS that styles it -- a two-surface problem that's easy to do inconsistently.

**How to avoid:**
1. Define breakpoints first (mobile < 768px, tablet 768-1024px, desktop > 1024px) and design the map-centric layout at each breakpoint BEFORE writing code.
2. For the map: on mobile, use a sticky/collapsible map that takes ~40% of viewport height at top; on desktop, use a side-panel layout (map 60%, content 40%).
3. Convert the most-changed UI components to CSS Grid/Flexbox with `minmax()` and `auto-fit` rather than fixed column counts in JS.
4. Test at exact breakpoints after every component change -- not just "does it look okay on my phone."

**Warning signs:**
- CSS has more than 3 `!important` overrides in responsive sections
- JS code has `window.innerWidth` checks to conditionally generate different HTML
- Map container has a fixed pixel height instead of viewport-relative units
- Horizontal scrolling appears at any viewport width

**Phase to address:**
Phase 3 (UI Redesign) -- establish the responsive grid system first, then fill in components

---

### Pitfall 4: Shareable Links Leak Private Trip Data

**What goes wrong:**
Implementing "public shareable links" by generating a token/slug and serving the trip at `/share/{token}` seems simple, but gets security wrong in subtle ways: the token is guessable (sequential IDs, short random strings), the shared view accidentally exposes user account info, or the share link grants more access than intended (edit instead of read-only).

**Why it happens:**
The current app uses JWT authentication for everything. Adding a "public" route that bypasses auth is an inversion of the security model. Developers often take shortcuts: reusing the same data-fetching code that returns full user context, or generating tokens that are too short (UUID v4 is fine, but truncating it isn't).

**How to avoid:**
1. Generate share tokens as full UUID v4 or 22+ character base64-encoded random bytes -- never sequential or short.
2. Create a dedicated `/api/shared/{token}` endpoint that returns a stripped-down trip view: no user info, no budget details, no edit capabilities. Do NOT reuse the authenticated `/api/travels/{id}` endpoint with a flag.
3. Store share tokens in the database with: `travel_id`, `created_at`, `expires_at` (optional), `created_by_user_id`. Allow users to revoke tokens.
4. The shared view frontend should be a separate, simpler page/component that cannot navigate to authenticated sections.
5. Rate-limit the shared endpoint to prevent enumeration attacks.

**Warning signs:**
- Share URL contains the travel's database ID (even alongside a token)
- Shared view returns JSON with `user_id`, `email`, or budget fields
- No revocation mechanism exists
- Share endpoint has no rate limiting

**Phase to address:**
Phase 4 (Sharing) -- design the data model and endpoint before building the UI

---

### Pitfall 5: Stop Editing Creates State Machine Chaos

**What goes wrong:**
Adding user control over AI-generated content (edit stops, reorder, regenerate) creates state consistency nightmares. The current job state machine (init -> plan -> select-stop -> confirm-route -> accommodations -> planning) is linear. Allowing edits mid-flow means: what happens to accommodations when a stop is removed? What happens to the day plan when stops are reordered? What about the budget split? The CONCERNS.md already flags "No Tests for Job State Machine" as high priority.

**Why it happens:**
The Redis job state is a single JSON blob modified by multiple endpoints without locking (race condition already noted in CONCERNS.md). Adding edit operations to an already-fragile state machine multiplies the ways state can become inconsistent. The `segment_budget`, `segment_index`, `leg_index` tracking is "complex and error-prone" per the existing analysis.

**How to avoid:**
1. Define state transitions explicitly: which edits are allowed at which phase. For example: stop reordering is only allowed before accommodation research starts. After accommodations are selected, editing a stop triggers a cascade that clears downstream data for that stop only.
2. Implement a `cascade_invalidation(stop_id)` function that knows which downstream data depends on each stop and clears it. Keep a dependency graph: stop -> accommodation -> day_plan -> guide.
3. Add optimistic locking to Redis job state (version counter checked on write).
4. Write state machine tests BEFORE implementing edit features -- the test coverage gap flagged in CONCERNS.md must be filled first.

**Warning signs:**
- Editing a stop shows stale accommodation data from the previous stop
- Budget totals don't update after removing a stop
- Day plans reference stops that no longer exist
- Two rapid edits result in a corrupted job state

**Phase to address:**
Phase 2 (User Control) -- but state machine tests should be written in Phase 1

---

### Pitfall 6: StopOptionsFinderAgent Uses Wrong Model (Existing Bug)

**What goes wrong:**
The StopOptionsFinderAgent hardcodes `"claude-haiku-4-5"` as the production model (`stop_options_finder.py:33`). Per CLAUDE.md and the agent model table, it should use `claude-sonnet-4-5` in production. This means stop quality is degraded even in production mode -- Haiku produces noticeably worse geographic reasoning than Sonnet.

**Why it happens:**
This is already identified in CONCERNS.md under "Technical Debt" but is worth elevating to a critical pitfall because it directly causes the "inconsistent stop quality" bug. The entire AI quality improvement effort will be undermined if the agent making stop recommendations is running on the cheapest model.

**How to avoid:**
Fix line 33 of `stop_options_finder.py`: change `get_model("claude-haiku-4-5", AGENT_KEY)` to `get_model("claude-sonnet-4-5", AGENT_KEY)`. This is a one-line fix that should be the very first change in the AI quality phase.

**Warning signs:**
- Stop suggestions are generic or geographically imprecise even in production mode
- Quality difference between RouteArchitect (Opus) and StopOptionsFinder (accidentally Haiku) is stark
- Logs show `claude-haiku-4-5` being used for `stop_options_finder` when TEST_MODE=false

**Phase to address:**
Phase 1 (AI Quality) -- fix immediately, before any prompt engineering work

---

### Pitfall 7: Travel Style Prompt Dilution

**What goes wrong:**
Users select specific travel styles (e.g., "Strand & Meer" / beach focus) but the StopOptionsFinderAgent's prompt buries this preference among many other constraints (drive time limits, geographic bounds, segment targets). Claude prioritizes the geographic and logistic constraints over style preferences, resulting in mountain village suggestions for a beach-focused trip.

**Why it happens:**
The current prompt structure lists travel styles as one line among many. Claude's instruction-following gives more weight to constraints that appear critical (drive time, geography) than preferences that appear optional (travel style). The system prompt emphasizes geographic correctness but says nothing about style fidelity.

**How to avoid:**
1. Elevate travel style to a CRITICAL constraint in the system prompt, not just the user prompt. Add: "KRITISCH: Vorgeschlagene Stopps MUESSEN zum Reisestil passen."
2. Include negative examples in the prompt: "Reisestil 'Strand & Meer' = NUR Küstenorte oder Inseln vorschlagen, KEINE Bergdörfer oder Binnenland-Städte."
3. Add a post-generation validation step: check if stop descriptions mention keywords aligned with the selected travel style. If not, re-prompt with explicit feedback.
4. Consider a style-specific prompt template rather than a generic one with style as a parameter.

**Warning signs:**
- Stop descriptions don't mention any travel-style-related activities
- All 3 suggested options for a "beach" trip are inland cities
- User feedback mentions "ignored my preferences"

**Phase to address:**
Phase 1 (AI Quality) -- part of prompt engineering improvements

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Broad `except Exception: pass` in utility functions | App never crashes on API failures | Silent failures make debugging impossible; expired API keys go unnoticed for days | Never -- always log at WARNING level minimum |
| Monolithic `main.py` (2614 lines) | No import complexity | Merge conflicts, slow navigation, difficult to test endpoints in isolation | Only in initial prototype; extract routers now |
| `innerHTML` string concatenation for UI | Fast to write, no build step | XSS risk (68 innerHTML sites), impossible to make responsive without rewriting strings | Acceptable for prototype; problematic for redesign |
| Redis job state without locking | Simple read-modify-write | Race conditions on concurrent edits (already flagged in CONCERNS.md) | Acceptable for single-user; breaks with edit features |
| In-memory fallback store without TTL | Dev works without Redis | Memory leak in production; tests pass but behavior diverges from Redis | Only for local dev; never in Docker deployment |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Google Directions API | Assuming driving mode always returns a route (fails for islands, pedestrian-only zones) | Check for `ZERO_RESULTS` status explicitly; have a fallback for water crossings |
| Google Geocoding API | Trusting the first result for ambiguous place names ("Porto" = Portugal or Porto, Greece?) | Use `components=country:XX` filter when the expected country is known; validate result coordinates against expected region |
| Claude API (stop generation) | Treating Claude's geographic claims as factual (coordinates, distances, drive times) | Always verify with Google APIs: geocode the name, compute actual driving distance, reject if > 20% off from Claude's claim |
| Google Places API | Silently returning empty results when API key lacks Places API activation | Log the actual API response status; distinguish "no results" from "API error" or "quota exceeded" |
| Redis job state | Reading stale state after concurrent writes from multiple endpoints | Use `WATCH`/`MULTI` transactions or add a version counter for optimistic locking |
| Anthropic rate limits | Firing 30+ parallel Claude calls per job without throttling | Use `asyncio.Semaphore(5)` to cap concurrent Claude API calls; existing `call_with_retry()` handles 429 but prevention is better |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded parallel Claude calls per job | 429 rate limit errors, retry storms, cascading delays | `asyncio.Semaphore` to limit concurrency to 5 calls | With 10+ stops (30+ parallel calls) |
| Health endpoint scanning all Redis keys | `/health` response time grows linearly with job count | Maintain an atomic counter instead of `KEYS job:*` | At 100+ accumulated jobs |
| Geocode cache is per-process, not shared | Same place geocoded repeatedly across Celery workers | Use Redis as geocode cache (already available) | With multiple Celery workers |
| Full trip JSON stored in single Redis key | Large JSON parse on every endpoint that reads job state | Acceptable at current scale; would need field-level access at scale | At 50+ concurrent jobs with 15+ stops each |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No job ownership verification (CONCERNS.md) | Any authenticated user can modify any job by guessing UUID | Add `_assert_job_owner(job, current_user)` after every `get_job()` |
| Google Maps API key exposed without auth | Key abuse, unexpected billing | Restrict key to referrers in GCP console; proxy all Maps calls through backend |
| Share tokens as sequential or short strings | Enumeration attacks expose all shared trips | Use UUID v4 or 22+ character crypto-random tokens |
| Settings endpoints not admin-restricted | Any user can change agent models and budget percentages | Change to `Depends(require_admin)` |
| Shared view returns full trip data including user info | Privacy leak to share recipients | Create a dedicated stripped-down response model for shared views |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Map is decorative, not interactive | Users can't click stops on map, can't visualize route changes | Map as primary navigation: click stop to see details, drag to reorder |
| No undo for destructive actions (delete stop, replace stop) | Accidental clicks lose AI-generated content that took minutes to produce | Soft-delete with undo toast (5-second window); keep previous version in state |
| Loading states without progress indication | Users don't know if AI is working or app is frozen (current SSE overlay helps, but only during initial planning) | Show per-action loading states: "Suche neue Optionen..." with estimated time |
| Regenerating content discards ALL previous options | User liked 2 of 3 options but wants a 3rd different one | "Keep these, find one more like X" instead of full regeneration |
| Mobile map covers entire screen with no way to see content | Map-centric design on mobile leaves no room for stop cards | Split-screen with draggable divider, or bottom sheet pattern (Google Maps style) |
| Stop cards lack visual hierarchy | All information presented equally; user can't scan quickly | Hero image + title + 2-3 key stats (drive time, nights, highlight activity); details on expand |

## "Looks Done But Isn't" Checklist

- [ ] **Ferry routing:** Route works for mainland trips but silently fails for island destinations -- test with "Greek Islands" and "Sardinia" specifically
- [ ] **Responsive layout:** Looks correct at 375px and 1440px but breaks at 768px (tablet) and 1024px (small laptop) -- test all 4 breakpoints
- [ ] **Share links:** Link works when clicked, but shared view still shows edit buttons or authenticated navigation -- test in incognito window
- [ ] **Stop editing:** Individual stop can be edited, but downstream data (accommodations, day plans) still shows stale content from the old stop -- verify cascade invalidation
- [ ] **Travel style fidelity:** Style is included in prompt, but generated stops don't match -- test with extreme styles ("nur Strand" for inland route, "Berge" for coastal route)
- [ ] **Budget recalculation:** Stop is added/removed but total budget split doesn't update -- verify `CostEstimate` recalculates
- [ ] **Map on mobile:** Map renders, but markers are too small to tap and polyline is invisible -- test on actual phone, not just browser DevTools
- [ ] **Error recovery:** AI returns malformed JSON for one stop option -- verify the other 2 options still display instead of showing a blank page

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| LLM geographic hallucination | LOW | Re-geocode with country filter; reject and re-prompt agent for that stop only |
| Ferry routing failure | MEDIUM | Manually split segment into mainland + ferry + island parts; add ferry port lookup |
| Responsive breakage on desktop | MEDIUM | Revert to desktop-only CSS; add mobile as progressive enhancement layer |
| Share token security flaw | LOW | Regenerate all tokens; add expiry; no data loss since shares are read-only |
| State machine corruption from edits | HIGH | Restart job from last consistent checkpoint; if none exists, restart from route confirmation |
| Wrong model on StopOptionsFinder | LOW | One-line fix; re-run affected trips to see quality improvement |
| Travel style not respected | LOW | Prompt change only; no code architecture change needed |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| LLM geographic hallucination | Phase 1 (AI Quality) | Geocoded coordinates within 50km of route corridor for all test destinations |
| Ferry routing failure | Phase 1 (AI Quality) | Greek Islands and Sardinia trips produce valid routes with ferry segments |
| Wrong model on StopOptionsFinder | Phase 1 (AI Quality) | Logs confirm `claude-sonnet-4-5` used when TEST_MODE=false |
| Travel style dilution | Phase 1 (AI Quality) | "Strand & Meer" trip to Mediterranean produces only coastal stops |
| State machine tests (prerequisite) | Phase 1 (AI Quality) | Full state machine test coverage before edit features are added |
| Stop editing state chaos | Phase 2 (User Control) | Edit a stop mid-flow; verify downstream data invalidated and regenerated |
| Responsive breaks desktop | Phase 3 (UI Redesign) | Visual regression tests at 375px, 768px, 1024px, 1440px |
| Mobile map UX | Phase 3 (UI Redesign) | Map usable on 375px screen: markers tappable, polyline visible, content accessible |
| Share token security | Phase 4 (Sharing) | Tokens are 22+ chars; shared view has no auth UI; revocation works |
| Share data leakage | Phase 4 (Sharing) | Shared endpoint returns no user_id, email, or budget internals |

## Sources

- [GDELT Project: LLM-Based Geocoders Struggle](https://blog.gdeltproject.org/generative-ai-experiments-why-llm-based-geocoders-struggle/) -- LLM geographic hallucination research
- [AFAR: Common Mistakes AI Makes When Planning Travel](https://www.afar.com/magazine/the-most-common-mistakes-ai-makes-when-planning-travel) -- AI travel planning failure modes
- [Varonis: The Dangers of Shared Links](https://www.varonis.com/blog/the-dangers-of-shared-links) -- Shared link security pitfalls
- [Code42: Security Pitfalls of Shared Public Links](https://www.code42.com/blog/security-pitfalls-of-shared-public-links/) -- Token enumeration risks
- [Google Maps Platform: RouteModifiers](https://developers.google.com/maps/documentation/routes_preferred/reference/rest/Shared.Types/RouteModifiers) -- Ferry routing API behavior
- Codebase analysis: `backend/agents/stop_options_finder.py:33` (hardcoded model bug)
- Codebase analysis: `backend/utils/maps_helper.py` (no ferry fallback, no coordinate validation)
- Codebase analysis: `.planning/codebase/CONCERNS.md` (security, reliability, test coverage gaps)

---
*Pitfalls research for: AI-powered road trip planner stabilization and UX redesign*
*Researched: 2026-03-25*
