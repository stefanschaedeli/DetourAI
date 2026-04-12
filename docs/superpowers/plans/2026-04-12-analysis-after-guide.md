# Analysis After Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the travel guide immediately after the day planner finishes, then run trip analysis in the background and inject its result into the already-visible guide.

**Architecture:** Move `job_complete` to fire before `TripAnalysisAgent` runs (with `trip_analysis: null`). After analysis finishes, send a new `analysis_complete` SSE event. The frontend's `onJobComplete` shows the guide immediately; a new `onAnalysisComplete` handler patches the analysis block into the DOM.

**Tech Stack:** Python/FastAPI backend · Vanilla JS frontend · SSE (Server-Sent Events)

---

## Files

| File | Change |
|------|--------|
| `backend/orchestrator.py` | Reorder: emit `job_complete` before analysis; add `analysis_complete` emit; persist merged plan |
| `contracts/sse-events.md` | Document new `analysis_complete` event |
| `frontend/js/communication/sse-client.js` | Add `analysis_complete` to `EVENTS` array |
| `frontend/js/communication/progress.js` | Add `onAnalysisComplete`; fix `onJobComplete` to not mark analysis done; register new handler |

---

## Task 1: Backend — reorder pipeline and emit `analysis_complete`

**Files:**
- Modify: `backend/orchestrator.py` (lines 405–431)

Current order (lines 405–431):
1. Log "Reiseplan fertig!"
2. Run TripAnalysisAgent → `plan["trip_analysis"] = result`
3. Inject token counts
4. Send `job_complete`

New order:
1. Inject token counts (move up)
2. Send `job_complete` (with `trip_analysis: null`)
3. Log analysis start
4. Run TripAnalysisAgent
5. Send `analysis_complete`
6. Persist merged plan back to Redis

- [ ] **Step 1: Apply the reorder**

Replace lines 400–431 in `backend/orchestrator.py` with:

```python
        # Merge all accommodation options into each stop
        for stop_dict in plan.get("stops", []):
            sid = stop_dict.get("id")
            stop_dict["all_accommodation_options"] = (pre_all_accommodation_options or {}).get(str(sid), [])

        await debug_logger.log(LogLevel.SUCCESS, "Reiseplan fertig!", job_id=job_id)

        # Inject token counts as internal metadata (before job_complete so they're in the initial payload)
        total_in  = sum(e["input"]  for e in self._token_accumulator)
        total_out = sum(e["output"] for e in self._token_accumulator)
        plan["_token_counts"] = {
            "total_input_tokens":  total_in,
            "total_output_tokens": total_out,
            "total_tokens":        total_in + total_out,
        }

        # Phase 4 kicks off AFTER job_complete so the guide is visible immediately
        plan["trip_analysis"] = None

        # Send job_complete — frontend shows the guide now
        await self.progress("job_complete", None, plan, 100)

        # Phase 4: Reise-Analyse (runs in background while user views the guide)
        await debug_logger.log(LogLevel.INFO, i18n_t("progress.analysis_start", lang),
                               job_id=job_id, message_key="progress.analysis_start")
        try:
            analysis_result = await TripAnalysisAgent(req, job_id, token_accumulator=self._token_accumulator).run(plan, req)
            plan["trip_analysis"] = analysis_result
        except Exception as exc:
            await debug_logger.log(LogLevel.WARNING,
                f"Reise-Analyse fehlgeschlagen (nicht kritisch): {exc}", job_id=job_id,
                message_key="progress.analysis_failed")
            plan["trip_analysis"] = None

        # Notify frontend of analysis result (null if failed — frontend guards on this)
        await self.progress("analysis_complete", None, {"trip_analysis": plan["trip_analysis"]}, 100)

        # Persist the merged plan (with trip_analysis) back to Redis so saved travels are complete
        job = self._load_job()
        job["plan"] = plan
        self._save_job(job)

        return plan
```

- [ ] **Step 2: Run the tests to make sure nothing broke**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass (the test suite mocks `TripAnalysisAgent` — the reorder doesn't affect mock behavior).

- [ ] **Step 3: Commit**

```bash
cd /Users/stefan/Code/Travelman3
git add backend/orchestrator.py
git commit -m "feat: job_complete vor Reise-Analyse senden, analysis_complete nachreichen

- job_complete wird direkt nach dem Day Planner gesendet (trip_analysis: null)
- TripAnalysisAgent läuft danach asynchron weiter
- Neues SSE-Event analysis_complete liefert das Analyse-Ergebnis nach
- Verarbeiteter Plan (inkl. trip_analysis) wird danach in Redis persistiert"
git tag v14.0.27
git push && git push --tags
```

Update `<span class="app-version">` in `frontend/index.html` to `v14.0.27` before committing.

---

## Task 2: Update SSE contract doc

**Files:**
- Modify: `contracts/sse-events.md`

- [ ] **Step 1: Add `analysis_complete` to the Terminal Events section**

In `contracts/sse-events.md`, find the Terminal Events table and add a new row. Also add a note that `job_complete` now carries `trip_analysis: null` and `analysis_complete` delivers the actual result.

Replace the Terminal Events table:

```markdown
### Terminal Events

| Event | Data Shape | Emitter | When |
|-------|------------|---------|------|
| `job_complete` | `{ result: TravelPlan }` (with `trip_analysis: null`) | `orchestrator` / `main.py` | Day planner done — guide is ready — **client must close SSE** |
| `analysis_complete` | `{ trip_analysis: TripAnalysis \| null }` | `orchestrator` | Trip analysis finished (or failed); patch into visible guide. Fires after `job_complete`. |
| `job_error` | `{ error: str }` | any component | Fatal failure occurred — **client must close SSE** |
```

- [ ] **Step 2: Commit**

```bash
cd /Users/stefan/Code/Travelman3
git add contracts/sse-events.md
git commit -m "docs: analysis_complete SSE-Event in Vertragsreferenz dokumentiert"
```

---

## Task 3: Register `analysis_complete` in SSE client

**Files:**
- Modify: `frontend/js/communication/sse-client.js` (line 22 — end of EVENTS array)

- [ ] **Step 1: Add `analysis_complete` to the EVENTS array**

In `sse-client.js`, find the `EVENTS` array (lines 11–23). Add `'analysis_complete'` to it:

```js
  const EVENTS = [
    'debug_log', 'route_ready', 'stop_done', 'agent_start', 'agent_done',
    'job_complete', 'job_error', 'accommodation_loading', 'accommodation_loaded',
    'accommodations_all_loaded', 'stop_research_started', 'activities_loaded',
    'restaurants_loaded', 'route_option_ready', 'route_options_done', 'ping',
    'leg_complete',
    'replace_stop_progress', 'replace_stop_complete',
    'remove_stop_progress',  'remove_stop_complete',
    'add_stop_progress',     'add_stop_complete',
    'reorder_stops_progress', 'reorder_stops_complete',
    'update_nights_progress', 'update_nights_complete',
    'style_mismatch_warning', 'ferry_detected',
    'analysis_complete',
  ];
```

- [ ] **Step 2: Commit**

```bash
cd /Users/stefan/Code/Travelman3
git add frontend/js/communication/sse-client.js
git commit -m "feat: analysis_complete in SSE-Client-Event-Liste registriert"
git tag v14.0.28
git push && git push --tags
```

Update `<span class="app-version">` in `frontend/index.html` to `v14.0.28`.

---

## Task 4: Frontend — handle `analysis_complete` in progress.js

**Files:**
- Modify: `frontend/js/communication/progress.js`

Three changes:
1. `onJobComplete` — remove the line that calls `_completeAnalysisTimelineRow()` (analysis isn't done yet)
2. Add new `onAnalysisComplete(data)` handler
3. Register `analysis_complete: onAnalysisComplete` in `connectSSE`

- [ ] **Step 1: Remove `_completeAnalysisTimelineRow()` from `onJobComplete`**

In `progress.js`, `onJobComplete` (line 157), remove the call to `_completeAnalysisTimelineRow()` on line 163. The function should now read:

```js
async function onJobComplete(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressOverlay.completeLine('trip_analysis', t('progress.analysis_complete'));
  progressOverlay.completeLine('day_planner',   t('progress.day_plan_complete'));
  progressOverlay.completeLine('guide_phase',   t('progress.guide_complete'));
  progressOverlay.completeLine('route_arch',    t('progress.route_confirmed'));
  overlaySetProgress(100);
  progressOverlay.close();
  S.result = data;
  if (typeof updateSidebar === 'function') updateSidebar();
  lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: data });
  markAllStopsDone();
  showLoading(t('progress.guide_preparing'));
  try {
    const saved = await apiSaveTravel(data);
    if (saved && saved.id) {
      data._saved_travel_id = saved.id;
      S.result = data;
      lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: data });
    }
  } catch (err) { console.warn('DB-Speicherung:', err.message); }
  const travelTitle = data.custom_name || data.title || '';
  showTravelGuide(data);
  showSection('travel-guide');
  if (data._saved_travel_id) Router.navigate(Router.travelPath(data._saved_travel_id, travelTitle));
  hideLoading();
}
```

- [ ] **Step 2: Add `onAnalysisComplete` handler after `onJobComplete`**

Insert the following function directly after `onJobComplete` (before `onJobError`):

```js
function onAnalysisComplete(data) {
  // Mark the analysis timeline row as done (may already be closed if overlay was dismissed)
  _completeAnalysisTimelineRow();

  if (!data || !data.trip_analysis) return;

  // Patch S.result so future re-renders have the analysis
  if (S.result) {
    S.result.trip_analysis = data.trip_analysis;
    lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: S.result });
  }

  // Inject analysis HTML into the already-visible overview collapsible body
  const body = document.querySelector('.overview-collapsible__body > div');
  if (!body) return;

  const analysisHtml = renderTripAnalysis(data.trip_analysis, S.result && S.result.request);
  if (!analysisHtml) return;

  // Replace existing .trip-analysis element, or prepend if not yet present
  const existing = body.querySelector('.trip-analysis');
  if (existing) {
    existing.outerHTML = analysisHtml;
  } else {
    body.insertAdjacentHTML('afterbegin', analysisHtml);
  }
}
```

- [ ] **Step 3: Register handler in `connectSSE`**

In `connectSSE` (line 200), add `analysis_complete` to the event map before `job_error`:

```js
    job_complete:           onJobComplete,
    analysis_complete:      onAnalysisComplete,
    job_error:              onJobError,
```

- [ ] **Step 4: Commit**

```bash
cd /Users/stefan/Code/Travelman3
git add frontend/js/communication/progress.js
git commit -m "feat: Reiseführer sofort anzeigen, Analyse per analysis_complete nachreichen

- onJobComplete ruft _completeAnalysisTimelineRow() nicht mehr auf
- Neuer Handler onAnalysisComplete patcht .trip-analysis ins DOM
- analysis_complete in connectSSE-Event-Map registriert"
git tag v14.0.29
git push && git push --tags
```

Update `<span class="app-version">` in `frontend/index.html` to `v14.0.29`.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `job_complete` fires after Day Planner (before analysis) | Task 1 |
| `analysis_complete` SSE event sent after TripAnalysisAgent | Task 1 |
| Redis plan updated after analysis (complete data persisted) | Task 1 |
| SSE contract doc updated | Task 2 |
| `analysis_complete` registered in SSEClient EVENTS | Task 3 |
| `onJobComplete` shows guide without analysis | Task 4 step 1 |
| `onAnalysisComplete` patches DOM | Task 4 step 2 |
| Handler registered in `connectSSE` | Task 4 step 3 |
| Analysis timeline row marked done in `onAnalysisComplete` | Task 4 step 2 |
| Error case: `trip_analysis: null` → `onAnalysisComplete` guards and exits early | Task 4 step 2 (the `if (!data || !data.trip_analysis) return` line) |

All spec requirements covered. No placeholders or TBDs found.

**Type consistency check:**
- `renderTripAnalysis(analysis, req)` — called in `guide-overview.js` line 49 and in the new `onAnalysisComplete`. Same signature. ✓
- `_completeAnalysisTimelineRow()` — defined in `progress.js`, called from `onAnalysisComplete`. Same file. ✓
- `S.result` — used throughout `progress.js`. ✓
- `LS_RESULT` — used throughout `progress.js`. ✓
- `lsSet` — used throughout `progress.js`. ✓
