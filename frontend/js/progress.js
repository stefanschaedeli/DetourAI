'use strict';

let progressSSE = null;
let stopProgress = {};  // stop_id → {activities: bool, restaurants: bool}

function connectSSE(jobId) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }

  progressSSE = openSSE(jobId, {
    route_ready:            onRouteReady,
    activities_loaded:      onActivitiesLoaded,
    restaurants_loaded:     onRestaurantsLoaded,
    stop_done:              onStopDone,
    stop_research_started:  onStopResearchStarted,
    agent_start:            onAgentStart,
    agent_done:             onAgentDone,
    job_complete:           onJobComplete,
    job_error:              onJobError,
    debug_log:              onProgressDebugLog,
    ping: () => {},
    onerror: () => { console.warn('Progress SSE error'); },
  });
}

function onProgressDebugLog(data) {
  S.logs.push(data);
  updateDebugLog();
  // Overlay-Zeilen aus bekannten Log-Nachrichten
  const msg = data.message || '';
  if (msg.includes('Orchestrator startet')) {
    progressOverlay.addLine('orchestrator', 'Planung wird gestartet…');
    progressOverlay.completeLine('orchestrator', '');
  } else if (msg.includes('RouteArchitect startet')) {
    progressOverlay.addLine('route_arch', 'Analysiere die Gesamtroute…');
  } else if (msg.match(/Forschungsphase:\s*(\d+)/)) {
    const n = msg.match(/Forschungsphase:\s*(\d+)/)[1];
    progressOverlay.addLine('research_phase', `Recherchiere Aktivitäten und Restaurants für ${n} Orte…`);
    progressOverlay.completeLine('research_phase', '');
  } else if (msg.match(/Reiseführer-Recherche für (\d+)/)) {
    const n = msg.match(/Reiseführer-Recherche für (\d+)/)[1];
    progressOverlay.addLine('guide_phase', `Schreibe Reiseführer für ${n} Orte…`);
  } else if (msg.includes('Tagesplaner startet')) {
    progressOverlay.completeLine('guide_phase', 'Reiseführer fertig');
    progressOverlay.addLine('day_planner', 'Erstelle den Tagesplan…');
  } else if (msg.includes('Reise-Analyse wird erstellt')) {
    progressOverlay.completeLine('day_planner', 'Tagesplan fertig');
    progressOverlay.addLine('trip_analysis', 'Reise-Analyse wird erstellt…');
    _addAnalysisTimelineRow();
  } else if (msg.includes('Reise-Analyse fehlgeschlagen')) {
    progressOverlay.completeLine('trip_analysis', 'übersprungen');
    _completeAnalysisTimelineRow();
  }
}

function onStopResearchStarted(data) {
  const region = data.region || '';
  if (data.section === 'activities') {
    progressOverlay.addLine('act_' + data.stop_id, `Aktivitäten für ${region}…`);
  } else if (data.section === 'restaurants') {
    progressOverlay.addLine('rest_' + data.stop_id, `Restaurants für ${region}…`);
  }
}

function onRouteReady(data) {
  const stops = data.stops || [];
  progressOverlay.completeLine('route_arch', 'Route festgelegt');
  buildStopsTimeline(stops);
}

function buildStopsTimeline(stops) {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline) return;

  stopProgress = {};
  stops.forEach(s => { stopProgress[s.id] = { activities: false, restaurants: false }; });

  timeline.innerHTML = stops.map(stop => {
    const flag = FLAGS[stop.country] || '';
    return `
      <div class="timeline-stop" id="timeline-stop-${stop.id}">
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <h4>${flag} ${esc(stop.region || stop.id)}</h4>
          <div class="timeline-status" id="timeline-status-${stop.id}">
            <div class="shimmer-line"></div>
            <div class="shimmer-line short"></div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function onActivitiesLoaded(data) {
  const stopId = data.stop_id;
  const region = data.region || '';
  const activities = data.activities || [];
  progressOverlay.completeLine('act_' + stopId, `${activities.length} Aktivitäten`);

  if (stopProgress[stopId]) stopProgress[stopId].activities = true;

  const status = document.getElementById(`timeline-status-${stopId}`);
  if (status) {
    const existing = status.innerHTML;
    const actHtml = `
      <div class="timeline-item done">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <span>${activities.length} Aktivitäten geladen</span>
      </div>
    `;
    status.innerHTML = actHtml + (stopProgress[stopId]?.restaurants
      ? status.querySelector('.restaurants-item')?.outerHTML || ''
      : '<div class="shimmer-line short"></div>');
  }
}

function onRestaurantsLoaded(data) {
  const stopId = data.stop_id;
  const restaurants = data.restaurants || [];
  progressOverlay.completeLine('rest_' + stopId, `${restaurants.length} Restaurants`);

  if (stopProgress[stopId]) stopProgress[stopId].restaurants = true;

  const status = document.getElementById(`timeline-status-${stopId}`);
  if (status) {
    const restHtml = `
      <div class="timeline-item done restaurants-item">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <span>${restaurants.length} Restaurants geladen</span>
      </div>
    `;
    // Remove shimmer
    const shimmer = status.querySelector('.shimmer-line.short');
    if (shimmer) shimmer.remove();
    status.insertAdjacentHTML('beforeend', restHtml);
  }
}

function onStopDone(data) {
  const stopId = data.stop_id;
  const stopEl = document.getElementById(`timeline-stop-${stopId}`);
  if (stopEl) stopEl.classList.add('done');
}

function onAgentStart(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) {
    el.textContent = data.message || 'Agent startet…';
  }
}

function onAgentDone(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) {
    el.textContent = data.message || 'Agent fertig.';
  }
}

function onJobComplete(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }

  // Complete any still-open overlay lines before closing
  progressOverlay.completeLine('trip_analysis', 'Analyse fertig');
  progressOverlay.completeLine('day_planner', 'Tagesplan fertig');
  progressOverlay.completeLine('guide_phase', 'Reiseführer fertig');
  progressOverlay.completeLine('route_arch', 'Route festgelegt');
  _completeAnalysisTimelineRow();
  progressOverlay.close();

  S.result = data;

  // Save to localStorage
  lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan: data });

  // Persist to DB (non-blocking, non-fatal)
  apiSaveTravel(data).catch(err => console.warn('DB-Speicherung:', err.message));

  markAllStopsDone();

  showLoading('Reiseführer wird aufbereitet…');
  setTimeout(() => {
    showTravelGuide(data);
    showSection('travel-guide');
    hideLoading();
  }, 800);
}

function onJobError(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }

  progressOverlay.close();

  const el = document.getElementById('progress-error');
  if (el) {
    el.style.display = 'block';
    el.textContent = 'Fehler: ' + (data.error || 'Unbekannter Fehler');
  }
}

function markAllStopsDone() {
  document.querySelectorAll('.timeline-stop').forEach(el => el.classList.add('done'));
}

function _addAnalysisTimelineRow() {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline || timeline.querySelector('#timeline-analysis')) return;
  timeline.insertAdjacentHTML('beforeend', `
    <div class="timeline-stop" id="timeline-analysis">
      <div class="timeline-dot"></div>
      <div class="timeline-content">
        <h4>Reise-Analyse</h4>
        <div class="timeline-status" id="timeline-status-analysis">
          <div class="shimmer-line short"></div>
        </div>
      </div>
    </div>
  `);
}

function _completeAnalysisTimelineRow() {
  const stopEl = document.getElementById('timeline-analysis');
  if (stopEl) stopEl.classList.add('done');
  const status = document.getElementById('timeline-status-analysis');
  if (status) {
    status.innerHTML = `
      <div class="timeline-item done">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <span>Analyse abgeschlossen</span>
      </div>
    `;
  }
}

function updateDebugLog() {
  if (!S.debugOpen) return;
  const log = document.getElementById('debug-log');
  if (!log) return;
  const recent = S.logs.slice(-50);
  log.innerHTML = recent.map(entry => {
    const level = entry.level || 'INFO';
    const msg   = entry.message || '';
    const agent = entry.agent ? `[${entry.agent}] ` : '';
    return `<div class="log-line log-${level.toLowerCase()}">${esc(agent)}${esc(msg)}</div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

function toggleDebugLog() {
  S.debugOpen = !S.debugOpen;
  const panel = document.getElementById('debug-panel');
  if (panel) panel.classList.toggle('open', S.debugOpen);
  if (S.debugOpen) updateDebugLog();
}

function cancelPlanning() {
  if (!confirm('Planung abbrechen und zum Formular zurückkehren?')) return;
  // Close any open SSE connection
  if (S._sseSource) { S._sseSource.close(); S._sseSource = null; }
  showSection('form-section');
}
