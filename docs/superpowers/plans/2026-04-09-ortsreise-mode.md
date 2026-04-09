# Ortsreise Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third planning mode "Ortsreise" — the user picks a single location, selects hotels, then gets a full activity/restaurant/day-plan deep-dive — plus a mode-picker landing page so users choose between Rundreise, Erkunden, and Ortsreise on first load.

**Architecture:** A new `"location"` leg mode is added to `TripLeg`; a slim backend endpoint `/api/plan-location/{job_id}` geocodes the location and builds a 1-stop `selected_stops` list, then sets the job status directly to `loading_accommodations` — skipping the entire route-building phase. From `loading_accommodations` onward the pipeline is identical to today. On the frontend a new `mode-picker.js` file renders the landing overlay; `form.js` gains an Ortsreise form branch and `submitLocationTrip()`; `state.js` tracks `S.appMode`.

**Tech Stack:** Python/FastAPI · Pydantic v2 · Vanilla JS · Google Places autocomplete · Redis job state · pytest · existing i18n system (de/en/hi)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/models/trip_leg.py` | Modify | Add `"location"` to `mode` Literal; update validators |
| `backend/models/travel_request.py` | Modify | Update `start_location`/`main_destination` properties + chain validator for `location` mode |
| `backend/main.py` | Modify | Add `POST /api/plan-location/{job_id}` endpoint |
| `backend/tests/test_models.py` | Modify | Tests for `location` leg validation |
| `backend/tests/test_endpoints.py` | Modify | Tests for new endpoint |
| `frontend/js/core/state.js` | Modify | Add `appMode`, `locationQuery`, `locationNights` to `S` |
| `frontend/js/core/router.js` | Modify | Root route shows mode-picker when `S.appMode` unset |
| `frontend/js/core/api.js` | Modify | Add `apiPlanLocation()` function |
| `frontend/js/features/mode-picker.js` | **Create** | Mode picker overlay — render, card click handlers, `initModePicker()` |
| `frontend/js/features/form.js` | Modify | Ortsreise form render; `buildPayload()` branch; `submitLocationTrip()` |
| `frontend/i18n/de.json` | Modify | 13 new keys |
| `frontend/i18n/en.json` | Modify | 13 new keys |
| `frontend/i18n/hi.json` | Modify | 13 new keys |
| `frontend/styles.css` | Modify | Mode picker overlay + card styles |
| `frontend/index.html` | Modify | Add `#mode-picker` section; add `mode-picker.js` script tag |

---

## Task 1: Backend — Add `"location"` leg mode to TripLeg

**Files:**
- Modify: `backend/models/trip_leg.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write failing tests for location leg validation**

Add to `backend/tests/test_models.py` after the existing explore leg tests:

```python
def test_location_leg_valid():
    """A location leg requires only start_location."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Paris, Frankreich",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
    )
    assert leg.mode == "location"
    assert leg.start_location == "Paris, Frankreich"


def test_location_leg_requires_start_location():
    """A location leg without start_location must fail validation."""
    with pytest.raises(ValidationError):
        TripLeg(
            leg_id="leg-0",
            start_location="",
            end_location="",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 8),
            mode="location",
        )


def test_location_leg_no_explore_description_needed():
    """A location leg must not require explore_description."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Lissabon, Portugal",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
        explore_description=None,
    )
    assert leg.explore_description is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_models.py::test_location_leg_valid tests/test_models.py::test_location_leg_requires_start_location tests/test_models.py::test_location_leg_no_explore_description_needed -v
```

Expected: `FAILED` with `ValidationError` (mode literal mismatch)

- [ ] **Step 3: Update `TripLeg.mode` and `validate_leg` in `backend/models/trip_leg.py`**

Change:
```python
mode: Literal["transit", "explore"]
```
to:
```python
mode: Literal["transit", "explore", "location"]
```

Update the `validate_leg` `@model_validator(mode="after")`:

```python
@model_validator(mode="after")
def validate_leg(self) -> "TripLeg":
    if self.end_date <= self.start_date:
        raise ValueError("end_date must be after start_date")
    if self.mode == "transit" and (not self.start_location or not self.end_location):
        raise ValueError("transit legs require start_location and end_location")
    if self.mode == "explore" and not self.explore_description:
        raise ValueError("explore legs require explore_description")
    if self.mode == "location" and not self.start_location:
        raise ValueError("location legs require start_location")
    return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python3 -m pytest tests/test_models.py::test_location_leg_valid tests/test_models.py::test_location_leg_requires_start_location tests/test_models.py::test_location_leg_no_explore_description_needed -v
```

Expected: All 3 `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/models/trip_leg.py backend/tests/test_models.py
git commit -m "feat: 'location'-Leg-Modus zu TripLeg hinzufügen

Neuer Leg-Modus 'location' für Ortsreise:
- mode Literal erweitert auf transit/explore/location
- validate_leg: location-Legs brauchen nur start_location
- Tests für gültige und ungültige location-Legs"
git tag v12.0.1 && git push && git push --tags
```

---

## Task 2: Backend — Update TravelRequest validators for `location` mode

**Files:**
- Modify: `backend/models/travel_request.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_models.py`:

```python
def test_travel_request_single_location_leg():
    """A TravelRequest with a single location leg must be valid."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Lissabon, Portugal",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 8),
        mode="location",
    )
    req = TravelRequest(legs=[leg], adults=2)
    assert req.start_location == "Lissabon, Portugal"
    assert req.main_destination == "Lissabon, Portugal"


def test_travel_request_location_leg_start_location_property():
    """start_location and main_destination return start_location for a location leg."""
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Amsterdam, Niederlande",
        end_location="",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        mode="location",
    )
    req = TravelRequest(legs=[leg], adults=1)
    assert req.start_location == "Amsterdam, Niederlande"
    assert req.main_destination == "Amsterdam, Niederlande"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_models.py::test_travel_request_single_location_leg tests/test_models.py::test_travel_request_location_leg_start_location_property -v
```

Expected: `FAILED`

- [ ] **Step 3: Update `start_location`, `main_destination`, and `validate_legs_chain` in `backend/models/travel_request.py`**

Update the two properties:

```python
@property
def start_location(self) -> str:
    leg = self.legs[0]
    if leg.mode == "explore":
        if leg.start_location and leg.start_location.strip():
            return leg.start_location.strip()
        return f"[Erkunden] {(leg.explore_description or '')[:50]}"
    if leg.mode == "location":
        return leg.start_location.strip()
    return leg.start_location.strip()

@property
def main_destination(self) -> str:
    leg = self.legs[-1]
    if leg.mode == "explore":
        return f"[Erkunden] {(leg.explore_description or '')[:50]}"
    if leg.mode == "location":
        return leg.start_location.strip()
    return leg.end_location.strip()
```

Update `validate_legs_chain`:

```python
@model_validator(mode='after')
def validate_legs_chain(self):
    for i in range(1, len(self.legs)):
        prev, curr = self.legs[i - 1], self.legs[i]
        # location legs have no end_location — skip chain validation involving them
        if prev.mode == "location" or curr.mode == "location":
            continue
        prev_end = prev.end_location.strip().lower() if prev.end_location else ""
        curr_start = curr.start_location.strip().lower() if curr.start_location else ""
        if prev_end and curr_start and prev_end != curr_start:
            raise ValueError(
                f"Leg {i} start_location must match leg {i-1} end_location "
                f"(got '{curr.start_location}' vs '{prev.end_location}')"
            )
        if curr.start_date != prev.end_date:
            raise ValueError(
                f"Leg {i} start_date must equal leg {i-1} end_date"
            )
    return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python3 -m pytest tests/test_models.py::test_travel_request_single_location_leg tests/test_models.py::test_travel_request_location_leg_start_location_property -v
```

Expected: Both `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All passing

- [ ] **Step 6: Commit**

```bash
git add backend/models/travel_request.py backend/tests/test_models.py
git commit -m "feat: TravelRequest-Validatoren für location-Leg-Modus anpassen

start_location/main_destination Properties und validate_legs_chain
unterstützen jetzt den location-Modus korrekt."
git tag v12.0.2 && git push && git push --tags
```

---

## Task 3: Backend — `POST /api/plan-location/{job_id}` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_endpoints.py`

- [ ] **Step 1: Check for `_async_return` helper in test_endpoints.py**

```bash
grep -n "_async_return\|async_return" backend/tests/test_endpoints.py | head -5
```

If not found, add near the top of `test_endpoints.py` (after imports):

```python
import asyncio

def _async_return(val):
    async def _inner(*args, **kwargs):
        return val
    return _inner
```

- [ ] **Step 2: Write failing tests**

Add to `backend/tests/test_endpoints.py`:

```python
def test_plan_location_valid(client, mocker):
    """POST /api/plan-location creates job and returns loading_accommodations."""
    mocker.patch(
        'main.geocode_google',
        side_effect=_async_return((48.8566, 2.3522, "place_abc"))
    )
    location_request = {
        "legs": [{
            "leg_id": "leg-0",
            "start_location": "Paris, Frankreich",
            "end_location": "",
            "start_date": "2026-07-01",
            "end_date": "2026-07-08",
            "mode": "location",
        }],
        "adults": 2,
        "children": [],
        "travel_styles": ["culture"],
        "accommodation_preferences": [],
        "budget_chf": 3000,
        "budget_accommodation_pct": 60,
        "budget_food_pct": 20,
        "budget_activities_pct": 20,
    }
    job_id_resp = client.post("/api/init-job", json=location_request)
    assert job_id_resp.status_code == 200
    job_id = job_id_resp.json()["job_id"]

    resp = client.post(f"/api/plan-location/{job_id}", json=location_request)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "loading_accommodations"
    assert data["job_id"] == job_id
    assert len(data["selected_stops"]) == 1
    assert data["selected_stops"][0]["region"] == "Paris, Frankreich"
    assert data["selected_stops"][0]["nights"] == 7


def test_plan_location_wrong_mode(client, mocker):
    """POST /api/plan-location must reject non-location legs with 400."""
    transit_request = {
        "legs": [{
            "leg_id": "leg-0",
            "start_location": "Zürich, Schweiz",
            "end_location": "Paris, Frankreich",
            "start_date": "2026-07-01",
            "end_date": "2026-07-08",
            "mode": "transit",
        }],
        "adults": 2,
        "children": [],
        "travel_styles": [],
        "accommodation_preferences": [],
        "budget_chf": 3000,
        "budget_accommodation_pct": 60,
        "budget_food_pct": 20,
        "budget_activities_pct": 20,
    }
    job_id_resp = client.post("/api/init-job", json=transit_request)
    assert job_id_resp.status_code == 200
    job_id = job_id_resp.json()["job_id"]

    resp = client.post(f"/api/plan-location/{job_id}", json=transit_request)
    assert resp.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_endpoints.py::test_plan_location_valid tests/test_endpoints.py::test_plan_location_wrong_mode -v
```

Expected: `FAILED` — 404 (endpoint not yet defined)

- [ ] **Step 4: Add `POST /api/plan-location/{job_id}` to `backend/main.py`**

Add after the `plan_trip` endpoint (around line 1235). `geocode_google` is already imported at the top of `main.py` via `from utils.maps_helper import geocode_google, ...`.

```python
# ---------------------------------------------------------------------------
# POST /api/plan-location/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/plan-location/{job_id}")
async def plan_location(job_id: str, request: TravelRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Ortsreise shortcut: geocode single location leg and jump to accommodation phase."""
    job = get_job(job_id)
    lang = _job_lang(job)

    if len(request.legs) != 1 or request.legs[0].mode != "location":
        raise HTTPException(status_code=400, detail=i18n_t("error.location_mode_required", lang))

    leg = request.legs[0]
    location = leg.start_location.strip()
    nights = (leg.end_date - leg.start_date).days

    geo = await geocode_google(location)
    if geo is None:
        raise HTTPException(status_code=422, detail=i18n_t("error.geocoding_failed", lang))
    lat, lon, place_id = geo

    stop = {
        "id": 1,
        "option_type": "city",
        "region": location,
        "country": "XX",
        "lat": lat,
        "lon": lon,
        "place_id": place_id,
        "drive_hours": 0,
        "drive_km": 0,
        "nights": nights,
        "arrival_day": 1,
        "highlights": [],
        "teaser": location,
        "is_fixed": True,
    }

    job["request"] = request.model_dump(mode="json")
    job["user_id"] = current_user.id
    job["selected_stops"] = [stop]
    job["stop_counter"] = 1
    job["status"] = "loading_accommodations"
    save_job(job_id, job)

    return {
        "job_id": job_id,
        "status": "loading_accommodations",
        "selected_stops": [stop],
    }
```

Find where backend i18n error messages live and add the two new keys:

```bash
grep -rn "not_loading_accommodations" backend/ | grep -v test | head -3
```

Add in the same i18n file:
```
"error.location_mode_required": "Dieser Endpunkt erfordert genau einen Leg im 'location'-Modus."
"error.geocoding_failed": "Der Ort konnte nicht geocodiert werden. Bitte überprüfe den Ortsnamen."
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python3 -m pytest tests/test_endpoints.py::test_plan_location_valid tests/test_endpoints.py::test_plan_location_wrong_mode -v
```

Expected: Both `PASSED`

- [ ] **Step 6: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All passing

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/tests/test_endpoints.py
git commit -m "feat: POST /api/plan-location Endpoint für Ortsreise hinzufügen

Geocodiert den Standort, erstellt 1-Stop selected_stops und setzt
Job-Status direkt auf loading_accommodations. Überspringt RouteArchitect
und StopFinder vollständig."
git tag v12.0.3 && git push && git push --tags
```

---

## Task 4: Frontend — Add `S.appMode` state and `apiPlanLocation()`

**Files:**
- Modify: `frontend/js/core/state.js`
- Modify: `frontend/js/core/api.js`
- Modify: `frontend/js/features/form.js`

- [ ] **Step 1: Add new fields to `S` in `frontend/js/core/state.js`**

Find the `const S = {` block and add three fields before the closing `};`:

```js
  // App mode — set by mode picker, persisted to localStorage
  appMode: null,              // "rundreise" | "erkunden" | "ortsreise" | null
  locationQuery: '',          // Ortsreise: raw location text input
  locationNights: 7,          // Ortsreise: number of nights
  ortsreiseDescription: '',   // Ortsreise: free-text description
```

Check if `LS_*` localStorage constants are defined in `state.js`:

```bash
grep -n "^const LS_" frontend/js/core/state.js | head -10
```

If so, add:
```js
const LS_APP_MODE = 'app_mode';
```

Also update the `// Provides:` header to list the new constants.

- [ ] **Step 2: Add `apiPlanLocation()` to `frontend/js/core/api.js`**

After `apiPlanTrip` (around line 130), add:

```js
/** Start an Ortsreise: geocode the single location and jump to accommodation phase. */
async function apiPlanLocation(payload, jobId) {
  const res = await _fetchQuiet(`${API}/plan-location/${encodeURIComponent(jobId)}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.json();
}
```

Add `apiPlanLocation` to the `// Provides:` header at the top of `api.js`.

- [ ] **Step 3: Update `clearAppData()` in `frontend/js/features/form.js`**

Find `clearAppData()` (around line 1031). Add these resets alongside `S.step = 1`:

```js
S.appMode = null;
S.locationQuery = '';
S.locationNights = 7;
S.ortsreiseDescription = '';
if (typeof lsClear === 'function') lsClear('app_mode');
```

- [ ] **Step 4: Commit**

```bash
git add frontend/js/core/state.js frontend/js/core/api.js frontend/js/features/form.js
git commit -m "feat: S.appMode State-Felder und apiPlanLocation() API-Funktion

Neue State-Felder appMode/locationQuery/locationNights/ortsreiseDescription,
localStorage-Persistenz für appMode, API-Client-Funktion für /api/plan-location."
git tag v12.0.4 && git push && git push --tags
```

---

## Task 5: Frontend — i18n keys

**Files:**
- Modify: `frontend/i18n/de.json`
- Modify: `frontend/i18n/en.json`
- Modify: `frontend/i18n/hi.json`

- [ ] **Step 1: Add German keys to `frontend/i18n/de.json`**

Insert after the `"login.*"` keys block:

```json
"mode_picker.title": "Wie möchtest du reisen?",
"mode_picker.subtitle": "Wähle den passenden Modus für deine Reise",
"mode_picker.rundreise.name": "Rundreise",
"mode_picker.rundreise.description": "A→B Roadtrip mit mehreren Stopps. Die KI plant die Strecke und findet die besten Orte auf dem Weg.",
"mode_picker.erkunden.name": "Erkunden",
"mode_picker.erkunden.description": "Freie Erkundung ab einem Startpunkt. Die KI wählt Regionen aus — du entscheidest, welche.",
"mode_picker.ortsreise.name": "Ortsreise",
"mode_picker.ortsreise.description": "Tauche tief in einen einzigen Ort ein. Hotels, Aktivitäten, Restaurants und Tagesplanung — alles für dein Reiseziel.",
"mode_picker.start_cta": "Starten",
"form.location_label": "Reiseziel",
"form.location_placeholder": "z.B. Lissabon, Portugal",
"form.nights_label": "Nächte",
"form.change_mode": "Modus wechseln"
```

- [ ] **Step 2: Add English keys to `frontend/i18n/en.json`**

```json
"mode_picker.title": "How would you like to travel?",
"mode_picker.subtitle": "Choose the right mode for your trip",
"mode_picker.rundreise.name": "Road Trip",
"mode_picker.rundreise.description": "A→B road trip with multiple stops. The AI plans the route and finds the best places along the way.",
"mode_picker.erkunden.name": "Explore",
"mode_picker.erkunden.description": "Free exploration from a starting point. The AI chooses regions — you decide which ones.",
"mode_picker.ortsreise.name": "Destination",
"mode_picker.ortsreise.description": "Deep dive into a single place. Hotels, activities, restaurants and day planning — all for your destination.",
"mode_picker.start_cta": "Start",
"form.location_label": "Destination",
"form.location_placeholder": "e.g. Lisbon, Portugal",
"form.nights_label": "Nights",
"form.change_mode": "Change mode"
```

- [ ] **Step 3: Add Hindi keys to `frontend/i18n/hi.json`**

```json
"mode_picker.title": "आप कैसे यात्रा करना चाहते हैं?",
"mode_picker.subtitle": "अपनी यात्रा के लिए सही मोड चुनें",
"mode_picker.rundreise.name": "रोड ट्रिप",
"mode_picker.rundreise.description": "A→B रोड ट्रिप कई पड़ावों के साथ। AI रास्ता बनाता है और रास्ते में सबसे अच्छी जगहें ढूंढता है।",
"mode_picker.erkunden.name": "एक्सप्लोर",
"mode_picker.erkunden.description": "शुरुआती बिंदु से मुक्त अन्वेषण। AI क्षेत्र चुनता है — आप तय करते हैं कौन से।",
"mode_picker.ortsreise.name": "गंतव्य यात्रा",
"mode_picker.ortsreise.description": "एक ही स्थान में गहरा उतरें। होटल, गतिविधियाँ, रेस्तरां और दिन की योजना — सब आपके गंतव्य के लिए।",
"mode_picker.start_cta": "शुरू करें",
"form.location_label": "गंतव्य",
"form.location_placeholder": "जैसे लिस्बन, पुर्तगाल",
"form.nights_label": "रातें",
"form.change_mode": "मोड बदलें"
```

- [ ] **Step 4: Verify JSON validity**

```bash
python3 -c "import json; json.load(open('frontend/i18n/de.json')); print('de OK')"
python3 -c "import json; json.load(open('frontend/i18n/en.json')); print('en OK')"
python3 -c "import json; json.load(open('frontend/i18n/hi.json')); print('hi OK')"
```

Expected: `de OK`, `en OK`, `hi OK`

- [ ] **Step 5: Commit**

```bash
git add frontend/i18n/de.json frontend/i18n/en.json frontend/i18n/hi.json
git commit -m "feat: i18n-Schlüssel für Mode-Picker und Ortsreise-Formular (de/en/hi)

13 neue Übersetzungsschlüssel für mode_picker.* und form.location_*
in allen drei unterstützten Sprachen."
git tag v12.0.5 && git push && git push --tags
```

---

## Task 6: Frontend — Mode picker styles

**Files:**
- Modify: `frontend/styles.css`

- [ ] **Step 1: Append mode picker CSS to `frontend/styles.css`**

Add at the end of `styles.css`:

```css
/* ---------------------------------------------------------------------------
   Mode Picker Overlay
   --------------------------------------------------------------------------- */

#mode-picker {
  position: fixed;
  inset: 0;
  background: var(--bg-primary, #000);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 9000;
  padding: var(--space-lg, 48px) var(--space-md, 24px);
  overflow-y: auto;
}

.mode-picker-overline {
  font-family: var(--font-body, sans-serif);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent-sky, #0a84ff);
  margin-bottom: 16px;
  text-align: center;
}

.mode-picker-title {
  font-family: var(--font-display, sans-serif);
  font-size: clamp(28px, 5vw, 48px);
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--text-primary, #f5f5f7);
  text-align: center;
  margin-bottom: 12px;
  line-height: 1.1;
}

.mode-picker-subtitle {
  font-family: var(--font-body, sans-serif);
  font-size: clamp(15px, 1.5vw, 18px);
  color: var(--text-secondary, #a1a1a6);
  text-align: center;
  margin-bottom: 56px;
  line-height: 1.5;
}

.mode-picker-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  max-width: 920px;
  width: 100%;
}

.mode-card {
  background: var(--bg-surface, #1d1d1f);
  border-radius: 20px;
  padding: 36px 28px 32px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  cursor: pointer;
  border: 1px solid rgba(255,255,255,0.06);
  transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94),
              box-shadow 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94),
              border-color 0.2s ease;
  text-align: left;
  opacity: 0;
  transform: translateY(20px);
  animation: modecardReveal 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
}

.mode-card:nth-child(1) { animation-delay: 0.05s; }
.mode-card:nth-child(2) { animation-delay: 0.15s; }
.mode-card:nth-child(3) { animation-delay: 0.25s; }

@keyframes modecardReveal {
  to { opacity: 1; transform: translateY(0); }
}

.mode-card:hover,
.mode-card:focus-visible {
  transform: translateY(-8px);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.5);
  border-color: rgba(10, 132, 255, 0.3);
  outline: none;
}

.mode-card-icon {
  width: 44px;
  height: 44px;
  color: var(--accent-sky, #0a84ff);
  margin-bottom: 20px;
}

.mode-card-icon svg {
  width: 44px;
  height: 44px;
}

.mode-card-name {
  font-family: var(--font-display, sans-serif);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary, #f5f5f7);
  margin-bottom: 10px;
  line-height: 1.2;
}

.mode-card-description {
  font-family: var(--font-body, sans-serif);
  font-size: 14px;
  line-height: 1.55;
  color: var(--text-secondary, #a1a1a6);
  margin-bottom: 28px;
  flex: 1;
}

.mode-card-cta {
  font-family: var(--font-body, sans-serif);
  font-size: 16px;
  font-weight: 500;
  color: var(--accent-sky, #0a84ff);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  transition: gap 0.2s ease;
}

.mode-card-cta::after {
  content: ' ›';
  font-size: 20px;
  transition: transform 0.2s ease;
}

.mode-card:hover .mode-card-cta::after {
  transform: translateX(4px);
}

.change-mode-link {
  font-family: var(--font-body, sans-serif);
  font-size: 13px;
  color: var(--text-muted, #86868b);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color 0.2s ease;
}

.change-mode-link:hover {
  color: var(--text-secondary, #a1a1a6);
}

.ortsreise-form-wrap {
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-lg, 48px) var(--space-md, 24px);
}

.ortsreise-submit-btn {
  width: 100%;
  margin-top: var(--space-lg, 48px);
}

@media (max-width: 767px) {
  .mode-picker-cards {
    grid-template-columns: 1fr;
    gap: 16px;
    max-width: 420px;
  }
  .mode-card {
    padding: 28px 24px 24px;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/styles.css
git commit -m "feat: Mode-Picker und Ortsreise-Formular Styles

Dark overlay, 3-Spalten Karten-Grid, lift-on-hover Animation,
staggered reveal, responsive single-column auf Mobile."
git tag v12.0.6 && git push && git push --tags
```

---

## Task 7: Frontend — Create `mode-picker.js`

**Files:**
- Create: `frontend/js/features/mode-picker.js`

- [ ] **Step 1: Create `frontend/js/features/mode-picker.js`**

```js
'use strict';

// Mode Picker — landing overlay for choosing Rundreise, Erkunden, or Ortsreise.
// Reads: S (state.js), t (i18n.js), showSection (state.js), Router (router.js),
//        lsSet (state.js), lsClear (state.js).
// Provides: initModePicker, showModePicker.

// ---------------------------------------------------------------------------
// SVG icon definitions (stroke-width 2, flat/clean, matches TRAVEL_STYLES)
// ---------------------------------------------------------------------------

const _MODE_ICONS = {
  rundreise: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18"/><polyline points="8 7 3 12 8 17"/><polyline points="16 7 21 12 16 17"/></svg>',
  erkunden:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
  ortsreise: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
};

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

/** Renders the mode picker cards into #mode-picker and wires click handlers. */
function initModePicker() {
  const el = document.getElementById('mode-picker');
  if (!el) return;

  const cards = ['rundreise', 'erkunden', 'ortsreise'].map(mode => `
    <div class="mode-card" data-mode="${mode}" role="button" tabindex="0"
         aria-label="${t('mode_picker.' + mode + '.name')}">
      <div class="mode-card-icon">${_MODE_ICONS[mode]}</div>
      <div class="mode-card-name">${t('mode_picker.' + mode + '.name')}</div>
      <div class="mode-card-description">${t('mode_picker.' + mode + '.description')}</div>
      <span class="mode-card-cta">${t('mode_picker.start_cta')}</span>
    </div>
  `).join('');

  el.innerHTML = `
    <div class="mode-picker-overline">${t('mode_picker.subtitle')}</div>
    <h1 class="mode-picker-title">${t('mode_picker.title')}</h1>
    <div class="mode-picker-cards">${cards}</div>
  `;

  el.querySelectorAll('.mode-card').forEach(card => {
    card.addEventListener('click', () => _selectMode(card.dataset.mode));
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _selectMode(card.dataset.mode); }
    });
  });
}

// ---------------------------------------------------------------------------
// Mode selection
// ---------------------------------------------------------------------------

function _selectMode(mode) {
  S.appMode = mode;
  if (typeof lsSet === 'function') lsSet('app_mode', mode);

  if (mode === 'ortsreise') {
    showSection('form-section');
    if (typeof renderOrtsreiseForm === 'function') renderOrtsreiseForm();
    Router.navigate('/form/ortsreise');
  } else {
    showSection('form-section');
    if (typeof initForm === 'function') initForm();
    if (typeof goToStep === 'function') goToStep(1);
    Router.navigate('/form/step/1');
  }
}

/** Show the mode picker overlay (e.g. from "Modus wechseln" link). */
function showModePicker() {
  S.appMode = null;
  if (typeof lsClear === 'function') lsClear('app_mode');
  showSection('mode-picker');
  initModePicker();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/js/features/mode-picker.js
git commit -m "feat: mode-picker.js — Modus-Auswahl Overlay

Drei Karten mit SVG-Icons (Rundreise/Erkunden/Ortsreise),
Klick-Handler setzen S.appMode und navigieren zum Formular."
git tag v12.0.7 && git push && git push --tags
```

---

## Task 8: Frontend — Ortsreise form and `submitLocationTrip()` in `form.js`

**Files:**
- Modify: `frontend/js/features/form.js`

- [ ] **Step 1: Check which helpers are available for reuse**

```bash
grep -n "function _renderTagInput\|function renderStep2\|function getAccPreferences\|function _renderAccPref\|function _setFieldError" frontend/js/features/form.js | head -10
```

Note the exact names — you will use them in the Ortsreise form.

- [ ] **Step 2: Add `renderOrtsreiseForm()` to `frontend/js/features/form.js`**

Add before the final section divider at the end of the file. Replace `_renderTagInput('mandatory')` etc. with whatever the actual helper names are from Step 1:

```js
// ---------------------------------------------------------------------------
// Ortsreise Form
// ---------------------------------------------------------------------------

/** Renders the single-page Ortsreise form inside #form-section. */
function renderOrtsreiseForm() {
  const el = document.getElementById('form-section');
  if (!el) return;

  // Ensure at least one leg object exists for date fields
  if (!S.legs[0]) S.legs[0] = { start_date: '', end_date: '', mode: 'location' };

  el.innerHTML = `
    <div class="ortsreise-form-wrap">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:var(--space-md,24px)">
        <h2 style="margin:0; font-size:28px; font-weight:700; letter-spacing:-0.02em">${t('mode_picker.ortsreise.name')}</h2>
        <button class="change-mode-link" onclick="showModePicker()">${t('form.change_mode')}</button>
      </div>

      <div class="form-group" style="margin-bottom:20px">
        <label class="form-label">${t('form.location_label')}</label>
        <input id="ortsreise-location" class="form-input" type="text"
          placeholder="${t('form.location_placeholder')}"
          value="${esc(S.locationQuery || '')}"
          autocomplete="off">
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px">
        <div class="form-group">
          <label class="form-label">${t('form.leg_start_date_label')}</label>
          <input id="ortsreise-start-date" class="form-input" type="date"
            value="${esc(S.legs[0].start_date || '')}">
        </div>
        <div class="form-group">
          <label class="form-label">${t('form.nights_label')}</label>
          <input id="ortsreise-nights" class="form-input" type="number"
            min="1" max="30" value="${S.locationNights || 7}">
        </div>
      </div>

      <div class="form-group" style="margin-bottom:20px">
        <label class="form-label">${t('form.adults_label')}</label>
        <div style="display:flex; align-items:center; gap:12px">
          <button class="stepper-btn" onclick="S.adults = Math.max(1, S.adults - 1); document.getElementById('ortsreise-adults-val').textContent = S.adults" aria-label="${t('form.decrease_adults_aria')}">−</button>
          <span id="ortsreise-adults-val" style="min-width:24px; text-align:center">${S.adults}</span>
          <button class="stepper-btn" onclick="S.adults = Math.min(20, S.adults + 1); document.getElementById('ortsreise-adults-val').textContent = S.adults" aria-label="${t('form.increase_adults_aria')}">+</button>
        </div>
      </div>

      <div class="form-group" style="margin-bottom:20px">
        <label class="form-label">${t('form.travel_style_label')}</label>
        <div class="style-grid">
          ${TRAVEL_STYLES.map(s => `
            <button class="style-btn ${S.travelStyles.includes(s.id) ? 'active' : ''}"
              data-style-id="${s.id}"
              onclick="toggleStyle('${s.id}', this)">
              ${s.icon}<span>${t('travel_styles.' + s.id) || s.label}</span>
            </button>
          `).join('')}
        </div>
      </div>

      <div class="form-group" style="margin-bottom:20px">
        <label class="form-label">${t('form.travel_description_label')}</label>
        <textarea id="ortsreise-description" class="form-input" rows="3"
          placeholder="${t('form.travel_description_placeholder')}"
        >${esc(S.ortsreiseDescription || '')}</textarea>
      </div>

      <div class="form-group" style="margin-bottom:20px">
        <label class="form-label">${t('form.accommodation_prefs_label')}</label>
        <input id="acc-pref-0" class="form-input" type="text" style="margin-bottom:8px"
          placeholder="${t('form.accommodation_pref1_placeholder')}"
          value="${esc((S.accommodationPrefs && S.accommodationPrefs[0]) || '')}">
        <input id="acc-pref-1" class="form-input" type="text" style="margin-bottom:8px"
          placeholder="${t('form.accommodation_pref2_placeholder')}"
          value="${esc((S.accommodationPrefs && S.accommodationPrefs[1]) || '')}">
        <input id="acc-pref-2" class="form-input" type="text"
          placeholder="${t('form.accommodation_pref3_placeholder')}"
          value="${esc((S.accommodationPrefs && S.accommodationPrefs[2]) || '')}">
      </div>

      <details style="margin-bottom:20px">
        <summary class="form-label" style="cursor:pointer">${t('form.advanced_toggle')}</summary>
        <div style="padding-top:12px; display:grid; grid-template-columns:1fr 1fr; gap:12px">
          <div class="form-group">
            <label class="form-label-sm">${t('header.max_activities_label')}</label>
            <input id="max-activities" class="input-sm" type="number" min="1" max="10" value="5">
          </div>
          <div class="form-group">
            <label class="form-label-sm">${t('header.max_restaurants_label')}</label>
            <input id="max-restaurants" class="input-sm" type="number" min="1" max="10" value="3">
          </div>
          <div class="form-group">
            <label class="form-label-sm">${t('form.hotel_radius_label')}</label>
            <input id="hotel-radius" class="input-sm" type="number" min="1" max="50" value="10">
          </div>
          <div class="form-group">
            <label class="form-label-sm">${t('header.log_verbosity_label')}</label>
            <select id="log-verbosity" class="input-sm">
              <option value="normal">${t('header.log_normal')}</option>
              <option value="minimal">${t('header.log_minimal')}</option>
              <option value="verbose">${t('header.log_verbose')}</option>
              <option value="debug">${t('header.log_debug')}</option>
            </select>
          </div>
        </div>
      </details>

      <button class="btn btn-primary ortsreise-submit-btn" onclick="submitLocationTrip()">
        ${t('form.submit')} →
      </button>
    </div>
  `;

  // Wire location input sync + Google Places autocomplete
  const locInput = document.getElementById('ortsreise-location');
  if (locInput) {
    locInput.addEventListener('input', () => { S.locationQuery = locInput.value; });
    _attachOrtsreiseAutocomplete(locInput);
  }
}

function _attachOrtsreiseAutocomplete(input) {
  if (typeof google === 'undefined' || !google.maps || !google.maps.places) return;
  const ac = new google.maps.places.Autocomplete(input, { types: ['geocode'] });
  ac.addListener('place_changed', () => {
    const place = ac.getPlace();
    if (place && place.formatted_address) {
      S.locationQuery = place.formatted_address;
      input.value = place.formatted_address;
    }
  });
}
```

Also update the `// Provides:` header at the top of `form.js` to include `renderOrtsreiseForm`.

- [ ] **Step 3: Add `submitLocationTrip()` to `frontend/js/features/form.js`**

Add after `renderOrtsreiseForm`:

```js
/** Validates and submits the Ortsreise form, then transitions to accommodation. */
async function submitLocationTrip() {
  const location = (document.getElementById('ortsreise-location')?.value || '').trim();
  if (!location) {
    alert(t('form.start_location_required'));
    return;
  }
  const startDate = document.getElementById('ortsreise-start-date')?.value;
  if (!startDate) {
    alert(t('form.start_date_required'));
    return;
  }

  // Sync state from inputs
  S.locationQuery = location;
  S.locationNights = parseInt(document.getElementById('ortsreise-nights')?.value) || 7;
  S.ortsreiseDescription = document.getElementById('ortsreise-description')?.value || '';

  const nights = S.locationNights;
  const endDate = _addDaysToDateStr(startDate, nights);

  const accPrefs = [
    document.getElementById('acc-pref-0')?.value || '',
    document.getElementById('acc-pref-1')?.value || '',
    document.getElementById('acc-pref-2')?.value || '',
  ].filter(p => p.trim());

  const payload = {
    legs: [{
      leg_id: 'leg-0',
      start_location: location,
      end_location: '',
      start_date: startDate,
      end_date: endDate,
      mode: 'location',
      via_points: [],
    }],
    total_days: nights + 1,
    adults: S.adults,
    children: S.children,
    travel_styles: S.travelStyles,
    travel_description: S.ortsreiseDescription,
    mandatory_activities: S.mandatoryTags.map(name => ({ name })),
    preferred_activities: S.preferredTags,
    max_activities_per_stop: parseInt(document.getElementById('max-activities')?.value) || 5,
    max_restaurants_per_stop: parseInt(document.getElementById('max-restaurants')?.value) || 3,
    activities_radius_km: 30,
    max_drive_hours_per_day: 4.5,
    proximity_origin_pct: 10,
    proximity_target_pct: 15,
    min_nights_per_stop: nights,
    max_nights_per_stop: nights,
    accommodation_preferences: accPrefs,
    hotel_radius_km: parseInt(document.getElementById('hotel-radius')?.value) || 10,
    budget_chf: 3000,
    budget_accommodation_pct: 60,
    budget_food_pct: 20,
    budget_activities_pct: 20,
    log_verbosity: document.getElementById('log-verbosity')?.value || 'normal',
    language: (typeof getLocale === 'function') ? getLocale() : 'de',
  };

  try {
    const initData = await apiInitJob(payload);
    S.jobId = initData.job_id;

    const data = await apiPlanLocation(payload, S.jobId);
    S.allStops = data.selected_stops || [];

    showSection('accommodation');
    Router.navigate('/accommodation/' + S.jobId);
    startAccommodationPhase(data);
    progressOverlay.open(t('accommodation.searching_options', { region: '' }));
    await connectAccommodationSSE(S.jobId);
    await apiStartAccommodations(S.jobId);
  } catch (err) {
    alert(t('form.trip_planning_error') + ' ' + (err.message || ''));
  }
}

/** Adds n calendar days to a YYYY-MM-DD string and returns a new YYYY-MM-DD string. */
function _addDaysToDateStr(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
```

Update the `// Provides:` header to also include `submitLocationTrip`.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/features/form.js
git commit -m "feat: renderOrtsreiseForm() und submitLocationTrip() in form.js

Einmaliges scrollbares Formular (Ort, Datum, Nächte, Teilnehmer,
Stile, Unterkunft, Erweitert). submitLocationTrip() ruft
apiInitJob + apiPlanLocation auf und leitet zur Unterkunftsauswahl."
git tag v12.0.8 && git push && git push --tags
```

---

## Task 9: Frontend — Wire `#mode-picker` into `index.html` and `router.js`

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/core/router.js`

- [ ] **Step 1: Add `#mode-picker` to `index.html`**

Find the `<div id="form-section"` tag. Add the mode picker section immediately before it:

```html
<!-- ── Mode Picker ─────────────────────────────────────────── -->
<div id="mode-picker" style="display:none"></div>
```

Find the script block with `/js/features/form.js` and add before it:

```html
<script src="/js/features/mode-picker.js"></script>
```

- [ ] **Step 2: Check how `showSection` hides/shows sections**

```bash
grep -n "function showSection\|'display'" frontend/js/core/state.js | head -10
```

Confirm `showSection('mode-picker')` will work correctly with the `style="display:none"` initialization.

- [ ] **Step 3: Update root route handler in `frontend/js/core/router.js`**

Find the handler for the root path `/` or `/form` (the case that currently calls `goToStep(1)` or `showSection('form-section')`). It will be inside a `_route()` or `_handle()` method or a `switch`/`if` block. Update the root case to:

```js
// Root: show mode picker if no mode chosen yet, else resume appropriate form
if (!S.appMode) {
  showSection('mode-picker');
  if (typeof initModePicker === 'function') initModePicker();
  return;
}
if (S.appMode === 'ortsreise') {
  showSection('form-section');
  if (typeof renderOrtsreiseForm === 'function') renderOrtsreiseForm();
  return;
}
// Rundreise or Erkunden — existing form flow
showSection('form-section');
if (typeof goToStep === 'function') goToStep(S.step || 1);
```

Add a `/form/ortsreise` route to the routes array (same format as existing routes):

```js
{ pattern: /^\/form\/ortsreise$/, handler: '_ortsreiseForm', section: 'form-section' },
```

Add the handler method in the Router object:

```js
_ortsreiseForm() {
  showSection('form-section');
  if (typeof renderOrtsreiseForm === 'function') renderOrtsreiseForm();
},
```

- [ ] **Step 4: Restore `S.appMode` from localStorage on app init**

Find where `S.step` or other persisted state is restored from localStorage at startup (either at the bottom of `router.js`, in the inline `<script>` in `index.html`, or in a DOMContentLoaded handler). Add alongside it:

```js
const _savedAppMode = (typeof lsGet === 'function') ? lsGet('app_mode') : null;
if (_savedAppMode) S.appMode = _savedAppMode;
```

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/js/core/router.js
git commit -m "feat: Mode-Picker in HTML und Router integriert

#mode-picker section, mode-picker.js script tag, Router zeigt
Mode-Picker wenn appMode null, Ortsreise-Form bei appMode=ortsreise,
appMode aus localStorage wiederhergestellt."
git tag v12.0.9 && git push && git push --tags
```

---

## Task 10: End-to-end smoke test

- [ ] **Step 1: Start backend**

```bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Open app — mode picker should appear**

Navigate to `http://localhost:8000` (or open `frontend/index.html` via Nginx). Verify:
- [ ] Mode picker overlay appears (full-screen dark background)
- [ ] 3 cards visible: Rundreise, Erkunden, Ortsreise
- [ ] SVG icons render correctly
- [ ] Hover lift animation works on each card

- [ ] **Step 3: Test Rundreise still works**

Click Rundreise → existing form step 1 appears. Confirm form works as before.

- [ ] **Step 4: Test Ortsreise flow end-to-end**

Click Ortsreise → Ortsreise form renders. Fill in:
- Location: "Lissabon, Portugal"
- Start date: a future date (e.g. 2026-07-01)
- Nights: 5
- 2 adults
- Select 1–2 travel styles

Click "Reise planen →". Verify in browser DevTools Network tab:
- [ ] `POST /api/init-job` → 200 with `job_id`
- [ ] `POST /api/plan-location/{job_id}` → 200 with `status: "loading_accommodations"`
- [ ] App transitions to accommodation section
- [ ] Accommodation panel shows "Lissabon, Portugal" with 5 nights

- [ ] **Step 5: Test "Modus wechseln" link**

In the Ortsreise form header, click "Modus wechseln" → mode picker appears again, `S.appMode` reset.

- [ ] **Step 6: Test localStorage persistence**

Choose Ortsreise, fill location, refresh page → Ortsreise form re-appears (not mode picker).

- [ ] **Step 7: Run final backend test suite**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All tests passing

- [ ] **Step 8: Final commit and tag**

```bash
git add -A
git status
# Only commit any remaining uncommitted changes
git commit -m "feat: Ortsreise-Modus vollständig implementiert

Komplettes Feature: Mode-Picker Landingpage, Ortsreise-Formular,
/api/plan-location Endpoint, location-Leg-Modus, i18n de/en/hi,
Apple-Design Styles. Pipeline ab Unterkunftsauswahl unverändert."
git tag v12.1.0 && git push && git push --tags
```

---

## Self-Review

**Spec coverage:**
- [x] Mode picker landing page, 3 cards, SVG icons, Apple design — Tasks 6, 7, 9
- [x] Ortsreise form: location, dates, nights, participants, styles, activities, acc prefs, advanced — Task 8
- [x] No budget field — Task 8 (fixed defaults in payload)
- [x] `"location"` leg mode in TripLeg — Task 1
- [x] TravelRequest validators for location mode — Task 2
- [x] `POST /api/plan-location` endpoint — Task 3
- [x] Jumps to `loading_accommodations`, existing pipeline unchanged — Task 3
- [x] `S.appMode` + localStorage persistence + `clearAppData` reset — Tasks 4, 9
- [x] `apiPlanLocation()` — Task 4
- [x] i18n 13 keys de/en/hi — Task 5
- [x] "Modus wechseln" link — Task 8
- [x] Staggered card animation — Task 6

**Name consistency:**
- `S.appMode`, `S.locationQuery`, `S.locationNights`, `S.ortsreiseDescription` — Tasks 4, 8
- `renderOrtsreiseForm()` — defined Task 8, called Tasks 7, 9
- `submitLocationTrip()` — defined Task 8, called from onclick in Task 8
- `showModePicker()` — defined Task 7, called from onclick in Task 8
- `initModePicker()` — defined Task 7, called in Task 9
- `apiPlanLocation()` — defined Task 4, called in Task 8
- `_addDaysToDateStr()` — defined and used in Task 8 only
