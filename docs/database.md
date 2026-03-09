# Travelman — Datenbank-Dokumentation

> Detaillierte Referenz zur SQLite-Persistenzschicht (`travels.db`)

---

## Overview

Travelman uses two persistence layers with distinct responsibilities:

| Store | Technology | TTL | Purpose |
|-------|-----------|-----|---------|
| **Job state** | Redis | 24 h | Live planning sessions, SSE event queues, agent intermediate results |
| **Travel history** | SQLite (`travels.db`) | Permanent | Completed trips the user has explicitly saved |

This document covers the SQLite layer only. Redis job state is ephemeral and not described here.

---

## File location

```
data/travels.db          # host path (Docker volume or local)
```

The path is controlled by the `DATA_DIR` environment variable (default: `<repo-root>/data/`).
The directory and the database file are created automatically on first backend start via `_init_db()`.

---

## Schema

### Table `travels`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `INTEGER` | No | autoincrement | Primary key |
| `job_id` | `TEXT` | No | — | UUID of the Redis planning job; `UNIQUE` — duplicate saves are silently ignored |
| `title` | `TEXT` | No | — | Auto-generated display title, format: `"Start → Destination (N Tage)"` |
| `created_at` | `TEXT` | No | — | UTC ISO-8601 timestamp at save time |
| `start_location` | `TEXT` | No | — | Trip start city/region (from `TravelPlan.start_location`) |
| `destination` | `TEXT` | No | — | Last stop's `region` field |
| `total_days` | `INTEGER` | No | — | Number of `DayPlan` entries in the plan |
| `num_stops` | `INTEGER` | No | — | Number of `TravelStop` entries |
| `total_cost_chf` | `REAL` | No | — | `CostEstimate.total_chf` |
| `plan_json` | `TEXT` | No | — | Full `TravelPlan` serialised as JSON |
| `has_travel_guide` | `INTEGER` | No | `0` | `1` if any stop contains a `travel_guide` narrative |
| `custom_name` | `TEXT` | Yes | `NULL` | User-defined display name (overrides `title` in the UI) |
| `rating` | `INTEGER` | No | `0` | Star rating set by the user, `0–5` |

**DDL (authoritative):**

```sql
CREATE TABLE IF NOT EXISTS travels (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    created_at     TEXT    NOT NULL,
    start_location TEXT    NOT NULL,
    destination    TEXT    NOT NULL,
    total_days     INTEGER NOT NULL,
    num_stops      INTEGER NOT NULL,
    total_cost_chf REAL    NOT NULL,
    plan_json      TEXT    NOT NULL,
    has_travel_guide INTEGER NOT NULL DEFAULT 0,
    UNIQUE(job_id)
);
-- Columns added via ALTER TABLE migrations (backwards-compatible):
-- custom_name TEXT
-- rating INTEGER NOT NULL DEFAULT 0
```

---

## Migrations

The schema is versioned via idempotent `ALTER TABLE … ADD COLUMN` blocks in `_init_db()`. Each block is wrapped in `try/except` so it silently skips if the column already exists. This means the database is always forwards-compatible — existing `travels.db` files from older versions gain new columns automatically on the next start.

```python
# backend/utils/travel_db.py — _init_db()
try:
    conn.execute("ALTER TABLE travels ADD COLUMN has_travel_guide INTEGER NOT NULL DEFAULT 0")
except Exception:
    pass
try:
    conn.execute("ALTER TABLE travels ADD COLUMN custom_name TEXT")
except Exception:
    pass
try:
    conn.execute("ALTER TABLE travels ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
except Exception:
    pass
```

---

## Data flow

### Save

```
User clicks "Reise speichern" in the travel guide
    → POST /api/travels  { plan: <TravelPlan JSON> }
    → save_travel(plan)
    → _sync_save(plan)
    → INSERT OR IGNORE INTO travels …
    ← { saved: true, id: 42 }   (or saved: false if job_id already exists)
```

`_build_title()` derives the display title from the plan at save time:

```python
f"{plan['start_location']} → {stops[-1]['region']} ({len(day_plans)} Tage)"
# e.g. "Liestal → Paris (10 Tage)"
```

### List

```
GET /api/travels
    → list_travels()
    → SELECT id, job_id, title, …, custom_name, rating FROM travels ORDER BY id DESC
    ← { travels: [ { id, title, custom_name, rating, … }, … ] }
```

Only metadata columns are returned — `plan_json` is excluded from the list response to keep payloads small.

### Load

```
GET /api/travels/{id}
    → get_travel(id)
    → SELECT plan_json FROM travels WHERE id=?
    ← Full TravelPlan object (deserialised from JSON)
```

### Update (rename / rate)

```
PATCH /api/travels/{id}  { custom_name?: string, rating?: 0-5 }
    → update_travel(id, custom_name, rating)
    → _sync_update(id, custom_name, rating)
    → UPDATE travels SET custom_name=?, rating=? WHERE id=?
    ← { updated: true, id: 42 }
```

`rating` is clamped server-side to `0–5`. An empty `custom_name` string is stored as `NULL` (falls back to the auto-generated `title` in the UI).

### Delete

```
DELETE /api/travels/{id}
    → delete_travel(id)
    → DELETE FROM travels WHERE id=?
    ← { deleted: true, id: 42 }
```

### Replan

```
POST /api/travels/{id}/replan
    → get_travel(id)     — loads full plan_json
    → reconstructs TravelRequest from saved plan fields
    → sets pre_built_stops + pre_selected_accommodations on job state
    → creates new Redis job (new job_id)
    → Celery task: only runs agents AFTER route/acc confirmation
    ← { job_id: "...", status: "planning_started", source_travel_id: 42 }
```

---

## `plan_json` — stored payload structure

The `plan_json` column stores the complete `TravelPlan` Pydantic model serialised to JSON. Key fields:

```jsonc
{
  "job_id": "uuid-string",
  "start_location": "Liestal, Schweiz",
  "start_lat": 47.486,
  "start_lng": 7.731,
  "google_maps_overview_url": "https://...",
  "stops": [                         // list of TravelStop
    {
      "id": 1,
      "region": "Grenoble",
      "country": "Frankreich",
      "arrival_day": 2,
      "nights": 2,
      "drive_hours_from_prev": 3.1,
      "drive_km_from_prev": 270,
      "lat": 45.188,
      "lng": 5.724,
      "accommodation": { /* StopAccommodation */ },
      "all_accommodation_options": [ /* list of raw dicts */ ],
      "top_activities": [ /* list of StopActivity */ ],
      "restaurants": [ /* list of Restaurant */ ],
      "travel_guide": { /* TravelGuide — optional */ },
      "further_activities": [ /* list of StopActivity — optional */ ],
      "google_maps_url": "https://...",
      "notes": "..."
    }
    // …
  ],
  "day_plans": [                     // list of DayPlan
    {
      "day": 1,
      "date": "2026-07-01",
      "type": "drive",
      "title": "Abfahrt Liestal → Grenoble",
      "description": "...",
      "stops_on_route": ["Basel", "Mulhouse"],
      "google_maps_route_url": "https://...",
      "time_blocks": [ /* list of TimeBlock */ ]
    }
    // …
  ],
  "cost_estimate": {
    "accommodations_chf": 1800,
    "ferries_chf": 0,
    "activities_chf": 640,
    "food_chf": 750,
    "fuel_chf": 360,
    "total_chf": 3550,
    "budget_remaining_chf": 1450
  },
  "outputs": {
    "pdf": "/outputs/trip-uuid.pdf",
    "pptx": "/outputs/trip-uuid.pptx"
  },
  "trip_analysis": { /* TripAnalysis — optional */ }
}
```

---

## Python API reference

All public functions are async and use `asyncio.to_thread()` to avoid blocking the FastAPI event loop. The underlying sync functions (`_sync_*`) are not part of the public API and should not be called directly.

```python
from utils.travel_db import save_travel, list_travels, get_travel, delete_travel, update_travel
```

### `save_travel(plan: dict) -> Optional[int]`

Inserts a new row. Returns the new `id` on success, `None` if `job_id` already exists (duplicate silently ignored).

### `list_travels() -> list[dict]`

Returns all rows ordered by `id DESC`, without `plan_json`. Each dict contains:
`id, job_id, title, created_at, start_location, destination, total_days, num_stops, total_cost_chf, has_travel_guide, custom_name, rating`

### `get_travel(travel_id: int) -> Optional[dict]`

Returns the full `TravelPlan` dict (deserialised from `plan_json`), or `None` if not found.

### `delete_travel(travel_id: int) -> bool`

Deletes the row. Returns `True` if a row was deleted, `False` if not found.

### `update_travel(travel_id: int, custom_name: Optional[str] = None, rating: Optional[int] = None) -> bool`

Updates `custom_name` and/or `rating` for the given row. Only fields that are not `None` are updated. Returns `True` if a row was updated, `False` if not found.

- `custom_name`: whitespace-trimmed; empty string stored as `NULL`
- `rating`: clamped to `0–5` (server-side `max(0, min(5, rating))`)

---

## REST API reference

All travel endpoints are under `/api/travels`.

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/api/travels` | — | `{ travels: Travel[] }` |
| `POST` | `/api/travels` | `{ plan: object }` | `{ saved: bool, id: int\|null }` |
| `PATCH` | `/api/travels/{id}` | `{ custom_name?: string, rating?: number }` | `{ updated: bool, id: int }` |
| `GET` | `/api/travels/{id}` | — | Full `TravelPlan` object |
| `DELETE` | `/api/travels/{id}` | — | `{ deleted: bool, id: int }` |
| `POST` | `/api/travels/{id}/replan` | — | `{ job_id: string, status: string, source_travel_id: int }` |

All endpoints return HTTP 404 with a German error detail if the `id` is not found.

---

## Frontend integration

The travels drawer is rendered by `frontend/js/travels.js`. It calls the following functions from `frontend/js/api.js`:

| JS function | HTTP call |
|-------------|-----------|
| `apiGetTravels()` | `GET /api/travels` |
| `apiGetTravel(id)` | `GET /api/travels/{id}` |
| `apiDeleteTravel(id)` | `DELETE /api/travels/{id}` |
| `apiUpdateTravel(id, data)` | `PATCH /api/travels/{id}` |
| `apiReplanTravel(id)` | `POST /api/travels/{id}/replan` |

The UI displays `custom_name` when set, falling back to the auto-generated `title`. Star rating is rendered as a clickable 0–5 widget; clicking the currently-active star resets the rating to 0.

---

## Backup & restore

The entire travel history is a single file:

```bash
# Backup
cp data/travels.db data/travels.db.bak

# Restore
cp data/travels.db.bak data/travels.db
```

In Docker the file lives in the `data` volume defined in `docker-compose.yml`.

---

*Back to [README](../README.md)*
