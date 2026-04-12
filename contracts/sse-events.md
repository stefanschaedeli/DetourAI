# SSE Events Reference

All SSE streams require authentication via the `?token=` query parameter.
`EventSource` does not support `Authorization` headers, so the JWT access
token is passed as a URL query parameter instead.

**Stream lifecycle:** The SSE stream stays open through `analysis_complete`. The client closes the `EventSource` connection when it receives `analysis_complete` or `job_error`. `job_complete` is no longer a terminal event — it fires first (guide ready), then `analysis_complete` follows (trip analysis patch).

---

## Events by Planning Phase

### Route Building Phase (emitter: `main.py` / `StopOptionsFinderAgent`)

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `ping` | _(no data)_ | `main.py` | Keepalive every 15 s while stream is open |
| `debug_log` | `{ message: str, level: str }` | `debug_logger` | Throughout all phases — verbose status messages |
| `route_option_ready` | `{ option: StopOption }` | `StopOptionsFinderAgent` | One event per stop option generated; streams incrementally |
| `route_options_done` | `{}` | `main.py` | All options for the current stop have been delivered |
| `stop_done` | `{ stop_index: int }` | `main.py` | User confirmed a stop; stop appended to route |
| `region_plan_ready` | `{ regions: RegionPlan[] }` | `RegionPlannerAgent` | After the initial multi-stop route is built; provides region groupings |
| `region_updated` | `{ region: RegionPlan }` | `main.py` | After the user replaces a region; single updated region |

### Accommodation Phase (emitter: `prefetch_accommodations` Celery task)

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `accommodation_loading` | `{ stop_index: int }` | `AccommodationResearcherAgent` | Starting accommodation fetch for a stop |
| `accommodation_loaded` | `{ stop_index: int, option: AccommodationOption }` | `AccommodationResearcherAgent` | One accommodation result is ready |
| `accommodations_all_loaded` | `{ stop_index: int }` | `AccommodationResearcherAgent` | All accommodations for this stop have been delivered |

### Full Planning Phase (emitter: `run_planning_job` Celery task / orchestrator)

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `stop_research_started` | `{ stop_index: int, stop_name: str }` | `orchestrator` | Beginning parallel research (activities + restaurants) for a stop |
| `activities_loaded` | `{ stop_index: int, activities: Activity[] }` | `ActivitiesAgent` | Activities research complete for a stop |
| `restaurants_loaded` | `{ stop_index: int, restaurants: Restaurant[] }` | `RestaurantsAgent` | Restaurant research complete for a stop |
| `leg_complete` | `{ leg_index: int }` | `orchestrator` | One trip leg fully planned (day plans generated) |
| `route_ready` | `{ stops: TravelStop[], geometry: str }` | `orchestrator` | Route confirmed with Google Directions geometry |

### Stop Replacement Phase (emitter: `replace_stop_job` Celery task)

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `replace_stop_progress` | `{ message: str }` | `replace_stop_job` | In-progress status update during stop replacement |
| `replace_stop_complete` | `{ stop: TravelStop }` | `replace_stop_job` | Stop replacement done; updated stop object returned |

### Terminal Events

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `job_complete` | `{ result: TravelPlan }` (with `trip_analysis: null`) | `orchestrator` / `main.py` | Day planner done — guide is ready — **client must close SSE** |
| `analysis_complete` | `{ trip_analysis: TripAnalysis \| null }` | `orchestrator` | Trip analysis finished (or failed); patch into visible guide. Fires after `job_complete`. |
| `job_error` | `{ error: str }` | any component | Fatal failure occurred — **client must close SSE** |

### Optional / Conditional Events

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `style_mismatch_warning` | `{ message: str }` | `main.py` | Travel style inconsistency detected in stop selection |
| `agent_start` | `{ agent: str }` | `orchestrator` | Agent lifecycle — agent about to run |
| `agent_done` | `{ agent: str, duration_ms: int }` | `orchestrator` | Agent lifecycle — agent finished |

---

## Data Type Shapes

```
StopOption       { name, lat, lon, country, description, why_visit, geheimtipp, ... }
RegionPlan       { region_name, stops: str[], nights: int }
AccommodationOption { name, type, price_per_night, booking_url, description, ... }
Activity         { name, duration_hours, cost_chf, description, category }
Restaurant       { name, cuisine, price_range, description }
TravelStop       { name, lat, lon, country, nights, day_plans: DayPlan[], ... }
TravelPlan       { stops: TravelStop[], total_cost_chf, legs: TripLeg[], ... }
```

---

## Notes

- All prices in CHF.
- `stop_index` is zero-based.
- `leg_index` is zero-based; a leg groups consecutive stops driven on the same day.
- `geometry` in `route_ready` is a Google-encoded polyline string.
- SSE endpoint URL pattern: `GET /api/progress/{job_id}/stream?token={jwt_access_token}`
