# Pitfalls Research

**Domain:** Multi-agent AI trip planner — adding intelligent day distribution, context forwarding, and recalculation
**Researched:** 2026-03-28
**Confidence:** HIGH (based on direct codebase analysis + known patterns in multi-agent LLM systems)

---

## Critical Pitfalls

### Pitfall 1: Nights-Per-Stop Budget Arithmetic Breaks When Days Are Redistributed

**What goes wrong:**
The Route Architect assigns `nights` per stop. Several downstream systems compute `arrival_day` by summing `nights` across the stop chain. If strategic day distribution changes `nights` without recomputing `arrival_day`, the hotel check-in dates (used in booking URLs), day plan headings, and the calendar view all silently go wrong. The bug is invisible at route-building time and only surfaces in the generated travel guide.

**Why it happens:**
`arrival_day` is set once by the Route Architect and stored in Redis job state. Many places reference it directly: `AccommodationResearcherAgent` computes `checkin = req.start_date + timedelta(days=arrival_day - 1)`, `DayPlannerAgent._build_stops()` uses it for day headings, and the frontend calendar renders it. When nights change post-selection, arrival_day is not recomputed along the chain.

**How to avoid:**
After any change to `nights` at a stop, recompute `arrival_day` for that stop and all subsequent stops before writing back to Redis. Write a single utility function `recompute_arrival_days(stops: list) -> list` that walks the stop list and fills in correct values. Use it everywhere nights are mutated — in the Route Architect response, in the recalculation endpoint, and in the user-facing "edit nights" flow.

**Warning signs:**
- Hotel check-in dates in booking URLs are wrong (check-in falls before trip start or is in the past)
- Calendar/week view shows overlapping or impossible day blocks
- Day plan headings like "Tag 5" appear for a stop that actually starts on day 7

**Phase to address:**
Strategic day distribution phase (first). Establish the `recompute_arrival_days()` utility before any other redistribution logic is written.

---

### Pitfall 2: Stale Redis Job State After Recalculation Causes Phantom Data

**What goes wrong:**
The Redis job state (`job:{job_id}`) is a large nested dict containing `selected_stops`, `segment_stops`, `route_geometry_cache`, `selected_accommodations`, and accommodation options. When a user changes nights or replaces a stop mid-planning, a partial update writes only the changed slice. The stale fields are then read back by subsequent operations, producing silently inconsistent results — e.g. an activity list researched for 2 nights is reused for a stop that now has 4 nights.

**Why it happens:**
`_load_job()` / `_save_job()` do a full read/write of the whole dict, which looks safe, but concurrent SSE consumers, the recalculation Celery task, and interactive endpoint handlers all call them independently. A read-modify-write race produces stale fields that never get overridden because nothing marks them dirty.

**How to avoid:**
Treat recalculation as a full pipeline invalidation, not a patch. When `nights` changes or a stop is replaced: (1) invalidate all cached research for that stop and all stops with higher `arrival_day` by deleting their keys from `selected_accommodations` and the activities cache; (2) mark affected stops with a `needs_replan: true` flag before writing back; (3) the recalculation task checks this flag and re-runs the research chain only for flagged stops. Never update a sub-key of the job state in isolation unless you explicitly intend partial update and document that invariant.

**Warning signs:**
- Activities or restaurants from an old stop appear in the guide for a different stop
- Accommodation prices reflect wrong number of nights (total_price_chf is based on old nights value)
- Route geometry cache returns distances for a stop sequence that no longer matches current stops

**Phase to address:**
Recalculation phase. Define the invalidation contract before writing any recalculation endpoint.

---

### Pitfall 3: Stop-Finder History Awareness Breaks the Streaming Partial-Parse Logic

**What goes wrong:**
`find_options_streaming()` uses a custom brace-counting parser (`_extract_next_option`) to emit options as they arrive in the token stream. If the prompt grows substantially (full stop history for long trips), Claude's response latency increases and the first option may arrive later in the stream. The streaming parser emits nothing to the frontend during this extended quiet period, making the UI appear frozen. Worse, if Claude responds with a preamble or wraps the JSON differently due to the richer prompt, the brace-counter fails to find any object until the full response is complete — defeating the streaming entirely.

**Why it happens:**
The streaming parser searches for `"options"\s*:\s*\[` as an anchor before counting braces. If the added history context causes Claude to respond with any non-JSON prefix (even a single whitespace change), the regex fails. The agent falls back to `parse_agent_json(final_text)` only after the full stream completes — meaning the user waits for the entire response before seeing anything.

**How to avoid:**
Keep the system prompt's `"Antworte AUSSCHLIESSLICH als valides JSON-Objekt"` constraint strong and test streaming with the full-history prompt before deploying. Add a timeout-based fallback: if no option is emitted within N seconds of the stream starting, push a `stream_slow` SSE event so the UI can show a spinner instead of silence. Validate streaming still works in TEST_MODE before any prompt change that grows history context.

**Warning signs:**
- Stop option cards appear all at once instead of one-by-one
- `Stream-Fehler` in `stop_options_finder.log`
- `"← Stream fertig in X.Xs — 0 Option(en) im Stream erkannt"` in logs despite a valid response

**Phase to address:**
Stop-finder history awareness phase. Run streaming validation as part of the definition of done.

---

### Pitfall 4: Previously Selected Stop Names Leak Into Option Suggestions (Deduplication Gap)

**What goes wrong:**
When the stop-finder is given the full history of selected stops, Claude will sometimes propose a city that was already selected — especially for common regional hubs (Nice, Lyon, Florence). The current prompt includes `stops_str` as context but does not explicitly forbid repeating those cities. The user sees an option card for a city they already have in their route.

**Why it happens:**
Claude treats `selected_stops` as informational context ("here is where you have been"), not as an exclusion list. Without an explicit negative constraint, the model pattern-matches to "good stops in this region" and re-proposes the same cities.

**How to avoid:**
Add an explicit exclusion line to the prompt: `"BEREITS GEWÄHLT (NICHT nochmals vorschlagen): [city1, city2, ...]"`. Place it immediately before the rules block so it has high positional weight. Also add a post-processing dedup step in `find_options()` and `find_options_streaming()` that checks each option's `region` against `selected_stops` (case-insensitive, strip country suffix) and filters it out before emitting to the frontend. Never rely solely on the prompt constraint — the post-processing guard is the reliable backstop.

**Warning signs:**
- A city appears both in the left-side "route so far" list and in the current option cards
- User reports a city was already selected and appeared again as an option
- In logs: option `region` matches a `region` already in `job["selected_stops"]`

**Phase to address:**
Stop-finder history awareness phase. The post-processing dedup belongs in `find_options()` / `find_options_streaming()`.

---

### Pitfall 5: Activity Wish Forwarding — Field Exists on TravelRequest But Agents Don't Read It

**What goes wrong:**
`TravelRequest` already has `preferred_activities: List[str]` and `mandatory_activities` fields. The Route Architect correctly inserts `mandatory_str` into its prompt. But `ActivitiesAgent`, `RestaurantsAgent`, and `DayPlannerAgent` do not receive these fields in their prompts — they only get the stop name and budget. Adding a global wishes field to the form without wiring it through every agent results in a field the user fills in that has zero effect downstream.

**Why it happens:**
Each agent builds its own prompt from the `TravelRequest` object, but the original agent authors only extracted the fields needed at that time. New fields added to `TravelRequest` are silently ignored unless each agent's `_build_prompt()` is updated. There is no contract test that verifies "if field X is set, it appears in the prompt".

**How to avoid:**
Before adding the global wishes field to the form, audit each agent's prompt builder: `route_architect.py`, `stop_options_finder.py`, `activities_agent.py`, `restaurants_agent.py`, `day_planner.py`, `travel_guide_agent.py`. For each agent, explicitly decide whether the wishes field should influence output, and if yes, add it to the prompt with a labelled block (e.g., `NUTZERWÜNSCHE`). Add a unit test in `test_agents_mock.py` that passes `preferred_activities=["hiking", "wine tasting"]` and asserts the word "hiking" appears in the captured prompt string.

**Warning signs:**
- User fills in wishes, resulting trip guide makes no mention of the requested activities
- `test_agents_mock.py` tests pass without the wishes field being present in mock prompts
- Log shows `preferred_activities: ['hiking']` in the request but the activities agent prompt contains none of those words

**Phase to address:**
Context forwarding phase. Audit all nine agents before writing any new UI field.

---

### Pitfall 6: Day Recalculation Triggered During Active SSE Stream Corrupts Job State

**What goes wrong:**
If a user opens the "edit nights" dialog while a planning Celery task is still running (unlikely but possible for long trips), the recalculation endpoint reads and writes `job:{job_id}` concurrently with the worker. Redis `setex` is atomic per-key, but the read-modify-write cycle is not. The worker's final `_save_job()` call overwrites the user's nights change, or vice versa.

**Why it happens:**
`_load_job()` / `_save_job()` use plain `GET` / `SETEX` without any optimistic locking or Redis transaction (`WATCH`/`MULTI`/`EXEC`). The existing code is safe only because all writes during active planning happen from one process (the Celery worker). Adding a second write path (the recalculation endpoint) breaks this assumption.

**How to avoid:**
Gate the recalculation endpoint behind a job status check: only allow recalculation when `job["status"] == "complete"`. Return HTTP 409 if the job is still running. This is simpler and more correct than implementing Redis optimistic locking. Document this constraint in the endpoint docstring.

**Warning signs:**
- Nights edit appears to succeed (200 response) but the guide still shows the old nights value
- Redis job state shows `status: running` after recalculation completes
- Celery worker logs show a `_save_job()` call timestamped after the recalculation endpoint's `_save_job()`

**Phase to address:**
Recalculation phase. Add the status gate as the first line of the recalculation endpoint handler.

---

### Pitfall 7: Hotel Geheimtipp Distance Enforcement Is Prompt-Only — No Server-Side Validation

**What goes wrong:**
The prompt instructs Claude that the Geheimtipp "MUSS innerhalb von {req.hotel_radius_km} km vom Zentrum von {region} liegen." Claude sometimes proposes a rural retreat 40-60 km away for scenic effect. Since there is no server-side distance check, the frontend shows a "secret tip" that is actually far outside the searched region, misleading users about proximity.

**Why it happens:**
The accommodation researcher does not geocode the proposed Geheimtipp and compare its coordinates to the stop's lat/lon. The lat/lon fields are not even requested in the Geheimtipp JSON schema (the current response format has no lat/lon for accommodation options). All distance enforcement is prompt-level only.

**How to avoid:**
Request `lat` and `lon` in the Geheimtipp JSON output (and optionally all options). After parsing, use the stop's `stop["lat"]`, `stop["lon"]` (already stored in the stop dict from the stop-finder) and compute the haversine distance to the proposed Geheimtipp. If it exceeds `hotel_radius_km * 1.5` (a generous tolerance), either discard the option and log a warning, or replace it with a generic "search nearby" result. The haversine formula is simple to inline or can reuse the bearing calculation already in `maps_helper.py`.

**Warning signs:**
- Geheimtipp descriptions mention "idyllisch abgelegen" or distances like "30 km außerhalb"
- User clicks Geheimtipp booking link and finds a property in a different town
- `accommodation_researcher.log` shows no coordinate validation step

**Phase to address:**
Hotel Geheimtipp quality phase. Add coordinate-based validation inside `enrich_option()`.

---

### Pitfall 8: Token Cost Spikes When History Context Is Added to Stop-Finder Calls

**What goes wrong:**
Each interactive stop selection triggers one or more `StopOptionsFinderAgent` calls. Adding the full stop history to each prompt grows input tokens linearly with the number of selected stops. For a 10-stop trip, the final stop-finder call sends roughly 3-4x the tokens of the first call. At claude-sonnet-4-5 pricing, a trip with many stops can cost significantly more than baseline, and hitting token quotas mid-trip is a real risk.

**Why it happens:**
The current prompt already includes `stops_str` (selected stops list), but additional context fields planned for v1.2 (user activity wishes, global notes, fuller stop descriptions) will further inflate the prompt. There is no trim or summarization of historical stop data before it is inserted.

**How to avoid:**
Cap the history context: pass only the last N stops (e.g., 5) in full, and reduce earlier stops to just `region (country)` tuples. The Stop-Finder only needs recent context for proximity checking — it does not need full details for stops from 8 days ago. Also audit the `max_tokens` budget for this agent (currently 4096) against actual response sizes in TEST_MODE logs before increasing context.

**Warning signs:**
- `call_with_retry` logs show input_tokens steadily increasing per stop selection for the same trip
- TOKEN_QUOTA_EXHAUSTED errors in middle of multi-stop trips
- TEST_MODE prompt capture shows prompt length > 3000 chars for a 6-stop trip

**Phase to address:**
Stop-finder performance optimization phase. Implement context trimming before adding full history.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Prompt-only constraint for Geheimtipp distance | No geocoding call needed | Claude ignores constraint ~20% of the time; users see misleading distances | Never — add server-side haversine validation |
| Reusing `arrival_day` from Route Architect without recomputation | Simpler code path | Booking dates wrong after any nights edit | Never — write `recompute_arrival_days()` utility |
| Deduplication via prompt instruction only | No extra post-processing | Claude re-proposes known stops regularly on long trips | Never for dedup — always add post-processing guard |
| Full job state blob in Redis without field-level locking | Simple read/write pattern | Race condition when recalculation endpoint writes concurrently with worker | Acceptable as long as recalculation is gated by job status check |
| Full stop history in prompt without trimming | Richer context for Claude | Token cost and latency grow linearly with stops | Acceptable only for trips <= 5 stops; trim for longer trips |

---

## Integration Gotchas

Common mistakes when connecting to existing system components.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Redis job state | Mutate sub-key in isolation e.g. `job["nights"][stop_id] = 3` | Always `_load_job()` -> mutate -> `_save_job()` as atomic read-modify-write |
| Anthropic streaming API | Assume prompt changes don't break the brace-counting parser | Re-test streaming after every prompt change that grows context; check logs for "0 Option(en) im Stream erkannt" |
| Google Directions in recalculation | Skip directions re-call for "unchanged" stops | Drive times depend on stop order; always recompute when sequence changes |
| `arrival_day` field | Treat it as a stable identifier for a stop | It is derived data; always recompute from `nights` chain when stops change |
| `stop["lat"]` / `stop["lon"]` | Trust these are always set on all stop objects | Route Architect stops may not have them until `DayPlannerAgent._enrich_with_google()` runs — check before using |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Parallel `asyncio.gather` for all stop research during recalculation | All stops re-researched at once; many concurrent Anthropic calls | Only re-research stops flagged `needs_replan: true` | Immediately for trips with > 4 stops being recalculated |
| Route geometry re-computation on every page load | Google Directions called on travel view open | Cache geometry in Redis job state (already done) — ensure recalculation doesn't bust cache unnecessarily | At ~10 view loads per session |
| Stop-finder prompt growing unbounded with history | claude-sonnet-4-5 input token cost rises; latency visible per stop selection | Cap history at last 5 stops in full; summarize older ones | Trips > 6 stops |
| Re-running Wikipedia enrichment during recalculation | Unnecessary Nominatim calls; 350ms sleep per call | Wikipedia enrichment runs only on new stops, not on recalculated existing stops | Trips > 3 stops being recalculated |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Recalculation runs in background with no feedback | User clicks "recalculate day plans" and sees nothing for 30 seconds | Fire an SSE progress event at start; show spinner in the affected day cards |
| Nights edit dialog uses `prompt()` with no validation | User enters "abc" or 0 — silent failure or NaN | Validate in the handler; clamp to `min_nights_per_stop` to `max_nights_per_stop` range before sending to backend |
| Map auto-fit on guide open animates before stops are rendered | Map fits to empty bounds, then jumps when stops load | Wait for stops to be painted before calling `map.fitBounds()` |
| Stop-finder showing all previous stops on map during selection | Map becomes cluttered for 8+ stop trips | Dim previously selected stops using the same marker opacity logic already in guide map-sync module |
| "Edit nights" tooltip appears on mobile only on tap, then disappears before user can click button | Mobile users cannot access nights editing | Use tap-to-toggle tooltip instead of hover-only; test on 375px viewport |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Strategic day distribution:** Verify the Route Architect JSON example in the prompt shows `nights` varying per region, not uniform `min_nights_per_stop` — Claude mimics the example format closely.
- [ ] **Context forwarding:** Verify each of the 9 agents' captured prompts (in TEST_MODE logs) contains the `preferred_activities` / wishes text when set — reading the code is not sufficient.
- [ ] **Deduplication:** Test a 6-stop trip end-to-end in TEST_MODE and confirm no city appears twice across all option rounds — unit tests of the dedup logic are necessary but not sufficient.
- [ ] **Recalculation:** After changing nights on stop 3 of 6, verify that `arrival_day` for stops 4, 5, 6 AND the hotel check-in dates in their booking URLs are all updated correctly.
- [ ] **Geheimtipp distance:** Generate 10 accommodation responses in TEST_MODE and check that `lat/lon` of the Geheimtipp is within `hotel_radius_km` of the stop center — not just that the prompt instruction is present.
- [ ] **Map auto-fit:** Test on a freshly loaded travel view (cold load) AND after navigating back from a stop drill-down — both paths call different map init sequences.
- [ ] **Stop-finder streaming:** After adding history context, confirm the first option card still appears within ~3 seconds in TEST_MODE — not just that the final response parses correctly.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Nights arithmetic broken (wrong booking dates) | MEDIUM | Add `recompute_arrival_days()` utility; run migration on any saved travels in SQLite that have wrong dates |
| Stale Redis state after recalculation | LOW | Gate recalculation on `status == "complete"`; add job state audit log at start of recalculation task |
| Streaming broken after prompt growth | LOW | Revert prompt change; extract history context into separate non-streaming pre-call if needed |
| Duplicate stop in options | LOW | Add post-processing dedup in `find_options()` — one function, no cascade changes needed |
| Geheimtipp too far from stop | LOW | Add haversine check in `enrich_option()`; fallback to dropping the option rather than showing wrong data |
| Token cost spike | LOW | Trim history context in `_build_prompt()` to last N stops |
| Race condition on recalculation | LOW | One-line status gate in recalculation endpoint handler |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Nights arithmetic / arrival_day recomputation | Strategic day distribution (Phase 1) | Check booking URL dates in TEST_MODE after nights edit |
| Stale Redis state during recalculation | Recalculation phase (Phase 5) | Run concurrent edit + recalculation test; verify final state |
| Streaming broken by richer history prompt | Stop-finder history awareness (Phase 3) | Confirm first card appears < 3s in TEST_MODE after prompt change |
| Duplicate stop suggestions | Stop-finder history awareness (Phase 3) | Run 6-stop trip; assert no city repeated across all option rounds |
| Activity wishes not forwarded | Context forwarding (Phase 2) | Capture prompts in TEST_MODE; assert wishes text present in each agent |
| Recalculation during active SSE stream | Recalculation phase (Phase 5) | Attempt recalculation while job is `running`; expect HTTP 409 |
| Geheimtipp distance violation | Hotel Geheimtipp quality (Phase 4) | Generate 10 accommodation sets; check haversine distance for each Geheimtipp |
| Token cost spike from history | Stop-finder performance (Phase 3) | Log input_tokens for stop 1 vs stop 6 in a 6-stop trip; assert < 2x ratio |

---

## Sources

- Direct codebase analysis: `backend/agents/route_architect.py`, `backend/agents/stop_options_finder.py`, `backend/agents/accommodation_researcher.py`, `backend/agents/day_planner.py`, `backend/orchestrator.py`, `backend/main.py`, `backend/models/travel_request.py`
- Known behaviour: Claude streaming API brace-counting parser in `find_options_streaming()` — fragile under prompt changes that affect output structure
- Known behaviour: `arrival_day` set once by Route Architect, never recomputed in current codebase
- Known behaviour: `lat`/`lon` not always present on Route Architect stops; enrichment runs later in `DayPlannerAgent._enrich_with_google()`
- Redis concurrency pattern: `_load_job()` / `_save_job()` in `orchestrator.py` — plain GET/SETEX, no optimistic locking

---
*Pitfalls research for: DetourAI v1.2 — multi-agent AI trip planner enhancements*
*Researched: 2026-03-28*
