# Ortsreise Mode — Design Spec

**Date:** 2026-04-09
**Status:** Approved
**Version target:** next minor after v12.0.0

---

## Overview

Introduce a third planning mode — **Ortsreise** — alongside the existing Rundreise (transit) and
Erkunden (explore) modes. The user picks a single location and gets a full deep-dive: hotel
selection, activities, restaurants, and a day-by-day plan — without building a multi-stop route.

A new **mode picker landing page** is added so the app guides users to the right mode on first
load, with plain-language explanations of when to use each.

---

## 1. Mode Picker Landing Page

### Trigger
Shown on app load when `S.appMode` is unset (i.e. no in-progress session). Replaces the direct
jump to `#form-section` that happens today.

### Structure
A full-screen centered overlay (`#mode-picker` section, `--bg-primary` background with
`backdrop-filter: blur`):

- **Overline:** `REISE PLANEN` — `--accent-sky`, uppercase, tracked (`.overline` class)
- **Headline:** e.g. "Wie möchtest du reisen?" — large, centered, display font
- **3 cards** in a horizontal row (stack to 1 column on mobile):

| Card | SVG Icon (24px, stroke-width 2) | Name | Description |
|------|---------------------------------|------|-------------|
| Rundreise | Route/path line icon | Rundreise | A→B Roadtrip mit mehreren Stopps entlang der Route. Die KI plant die Strecke und findet die besten Orte. |
| Erkunden | Compass-rose icon | Erkunden | Freie Erkundung ab einem Startpunkt. Die KI wählt Regionen aus — du entscheidest, welche. |
| Ortsreise | Location-pin icon | Ortsreise | Tieftauchen in einen einzigen Ort. Hotels, Aktivitäten, Restaurants und Tagesplanung — alles für dein Reiseziel. |

- Each card: `--bg-surface` (#1d1d1f), `border-radius: 20px`, `lift-on-hover`, staggered
  fade-in (`.stagger`, 0.1s delay per card)
- Each card has a **"Starten →"** link-style CTA (`--accent-sky`, `.cta-primary` style)
- SVG icons use `stroke="currentColor"`, `stroke-width="2"`, flat/clean style matching the
  existing TRAVEL_STYLES icons in `state.js`

### Re-triggering
A **"Modus wechseln"** link in the form header (small, `--text-secondary`) calls
`showSection('mode-picker')` and clears `S.appMode`.

### Implementation
- New `#mode-picker` section in `index.html`
- New file `frontend/js/features/mode-picker.js` — owns render + card click handlers,
  exports `initModePicker()`
- Loaded before `form.js` in `index.html` script order

---

## 2. Ortsreise Form

A **single-page scrollable form** (no step wizard, no progress bar) rendered inside
`#form-section` when `S.appMode === "ortsreise"`.

### Fields

| Field | Input | Notes |
|-------|-------|-------|
| Location | Text + Google Places autocomplete | Required. Same autocomplete as existing start/end fields. |
| Start date | Date picker | Required. |
| Nights | Number stepper, 1–30 | Required. Label: "Nächte". End date derived by frontend. |
| Participants | Adults + children | Same component as today's step 2. |
| Travel styles | Multi-select grid | Same `TRAVEL_STYLES` grid. |
| Must-have activities | Tag input | Same mandatory tags component. |
| Preferred activities | Tag input | Same preferred tags component. |
| Travel description | Textarea (optional) | Same free-text field. |
| Accommodation preferences | Checkbox group | Same `getAccPreferences()`. |
| Advanced settings | Collapsed section | Max activities/restaurants per stop, hotel radius, log verbosity — same fields as today's step 4. |

### Excluded fields
Budget (all budget fields), route-specific settings (max drive hours, proximity %, min/max
nights per stop), legs.

### Submit
Single **"Reise planen →"** pill button (`.cta-secondary`) at the bottom. Calls a new
`submitLocationTrip()` function in `form.js` (consistent with `submitTrip()` living there today).

---

## 3. Backend — Data Model

### TripLeg.mode
```python
mode: Literal["transit", "explore", "location"]
```

A `location` leg:
- `start_location` = chosen place (required, geocoded)
- `end_location` = `""` (ignored)
- `start_date` = arrival date
- `end_date` = `start_date + nights` (computed by frontend)
- `via_points = []`
- `explore_description = None`

### Validators
- `validate_leg`: `location` mode requires only `start_location` (no `end_location`,
  no `explore_description`)
- `validate_legs_chain`: single `location` leg is exempt from chain validation
- Root validator first/last-leg explore checks: `location` mode treated same as `explore`
  (allowed at start/end of a trip — and for Ortsreise it is the only leg)

### New endpoint: `POST /api/plan-location/{job_id}`
Slim alternative to `/api/plan-trip` for Ortsreise payloads:
1. Validates the request (single location leg)
2. Geocodes `start_location` using existing `geocode_location()` util → extracts `lat`, `lng`, `place_id`, `formatted_address`
3. Constructs 1-item `selected_stops` list in the same dict shape RouteArchitect produces:
   `{ "id": 1, "location": <formatted_address>, "lat": ..., "lng": ..., "place_id": ..., "nights": <locationNights>, "arrival_day": 1, "country": <country_code> }`
4. Stores request + selected_stops in Redis job
5. Sets `job["status"] = "loading_accommodations"`
6. Returns `{ job_id, status: "loading_accommodations" }`

From `loading_accommodations` onward the pipeline is **identical** to today:
prefetch accommodations → user picks hotel → `confirm-accommodations` → research +
day planning + analysis.

### No orchestrator changes needed
The location shortcut lives entirely in the new endpoint. The orchestrator's
`_run_research_and_planning()` receives a `pre_built_stops` list and proceeds normally.

---

## 4. Routing, State & i18n

### State additions to `S`
```js
S.appMode        // "rundreise" | "erkunden" | "ortsreise" | null
S.locationQuery  // string — raw location input for Ortsreise
S.locationNights // number — nights for Ortsreise
```

`S.appMode` persists to `localStorage`. Cleared by `clearAppData()`.

### Router
Root route (`/`) checks `S.appMode`: if unset → `showSection('mode-picker')`, else existing
behaviour. All other routes (`/form/step/1`, `/route-builder`, etc.) unchanged.

### i18n keys (de / en / hi required)
```
mode_picker.title
mode_picker.subtitle
mode_picker.rundreise.name
mode_picker.rundreise.description
mode_picker.erkunden.name
mode_picker.erkunden.description
mode_picker.ortsreise.name
mode_picker.ortsreise.description
mode_picker.start_cta
form.location_label
form.location_placeholder
form.nights_label
form.change_mode
```

---

## 5. Out of Scope

- No budget tracking for Ortsreise (no budget field, agents work unconstrained)
- No multi-stop Ortsreise (exactly 1 location)
- No replan/replace-stop for Ortsreise trips in saved travels (future work)
- No changes to the Erkunden or Rundreise flows

---

## 6. File Change Summary

| File | Change |
|------|--------|
| `frontend/index.html` | Add `#mode-picker` section; add `mode-picker.js` script tag |
| `frontend/js/features/mode-picker.js` | **New** — mode picker render + handlers |
| `frontend/js/features/form.js` | Ortsreise form render; `buildPayload()` branch; `submitLocationTrip()` |
| `frontend/js/core/state.js` | Add `appMode`, `locationQuery`, `locationNights` to `S` |
| `frontend/js/core/router.js` | Root route checks `S.appMode` |
| `frontend/i18n/de.json` | 13 new keys |
| `frontend/i18n/en.json` | 13 new keys |
| `frontend/i18n/hi.json` | 13 new keys |
| `frontend/styles.css` | Mode picker overlay + card styles |
| `backend/models/trip_leg.py` | Add `"location"` to `mode` Literal; update validators |
| `backend/main.py` | New `POST /api/plan-location/{job_id}` endpoint |
| `contracts/api-contract.yaml` | Document new endpoint |
| `backend/tests/` | Tests for new endpoint + location leg validation |
