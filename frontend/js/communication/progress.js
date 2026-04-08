'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let progressSSE  = null;
let stopProgress = {};  // stop_id => {activities: bool, restaurants: bool}

// ---------------------------------------------------------------------------
// UI: Debug log panel
// ---------------------------------------------------------------------------

function updateDebugLog() {
  if (!S.debugOpen) return;
  const log = document.getElementById('debug-log');
  if (!log) return;
  const recent = S.logs.slice(-50);
  log.innerHTML = recent.map(entry => {
    const level = entry.level || 'INFO';
    const agent = entry.agent ? '[' + entry.agent + '] ' : '';
    return '<div class="log-line log-' + level.toLowerCase() + '">' + esc(agent) + esc(entry.message || '') + '</div>';
  }).join('');
  log.scrollTop = log.scrollHeight;
}

function toggleDebugLog() {
  S.debugOpen = !S.debugOpen;
  const panel = document.getElementById('debug-panel');
  if (panel) panel.classList.toggle('open', S.debugOpen);
  if (S.debugOpen) updateDebugLog();
}

// ---------------------------------------------------------------------------
// UI: Stops timeline
// ---------------------------------------------------------------------------

function buildStopsTimeline(stops) {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline) return;
  stopProgress = {};
  stops.forEach(s => { stopProgress[s.id] = { activities: false, restaurants: false }; });
  timeline.innerHTML = stops.map(stop => {
    const flag = FLAGS[stop.country] || '';
    return '<div class="timeline-stop" id="timeline-stop-' + stop.id + '">'
      + '<div class="timeline-dot"></div>'
      + '<div class="timeline-content">'
      + '<h4>' + flag + ' ' + esc(stop.region || stop.id) + '</h4>'
      + '<div class="timeline-status" id="timeline-status-' + stop.id + '">'
      + '<div class="shimmer-line"></div><div class="shimmer-line short"></div>'
      + '</div></div></div>';
  }).join('');
}

function markAllStopsDone() {
  document.querySelectorAll('.timeline-stop').forEach(el => el.classList.add('done'));
}

function _addAnalysisTimelineRow() {
  const timeline = document.getElementById('progress-timeline');
  if (!timeline || timeline.querySelector('#timeline-analysis')) return;
  timeline.insertAdjacentHTML('beforeend',
    '<div class="timeline-stop" id="timeline-analysis">'
    + '<div class="timeline-dot"></div>'
    + '<div class="timeline-content">'
    + '<h4>' + t('progress.analysis_label') + '</h4>'
    + '<div class="timeline-status" id="timeline-status-analysis">'
    + '<div class="shimmer-line short"></div>'
    + '</div></div></div>'
  );
}

function _completeAnalysisTimelineRow() {
  const stopEl = document.getElementById('timeline-analysis');
  if (stopEl) stopEl.classList.add('done');
  const status = document.getElementById('timeline-status-analysis');
  if (status) {
    status.innerHTML = '<div class="timeline-item done">'
      + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>'
      + '<span>' + t('progress.analysis_complete') + '</span>'
      + '</div>';
  }
}

function cancelPlanning() {
  if (!confirm(t('progress.confirm_cancel'))) return;
  if (S._sseSource) { S._sseSource.close(); S._sseSource = null; }
  Router.navigate('/');
}

// ---------------------------------------------------------------------------
// SSE event handlers
// ---------------------------------------------------------------------------

function onProgressDebugLog(data) {
  S.logs.push(data);
  updateDebugLog();
  const key   = data.message_key || '';
  const count = (data.data && data.data.count) ? data.data.count : 0;
  if      (key === 'progress.orchestrator_start')    { progressOverlay.addLine('orchestrator',  t('progress.orchestrator_starting')); progressOverlay.completeLine('orchestrator', ''); }
  else if (key === 'progress.route_architect_start') { progressOverlay.addLine('route_arch',     t('progress.route_analysis')); }
  else if (key === 'progress.research_phase')        { progressOverlay.addLine('research_phase', t('progress.research_activities', {count})); progressOverlay.completeLine('research_phase', ''); }
  else if (key === 'progress.guide_writing')         { progressOverlay.addLine('guide_phase',    t('progress.guide_writing', {count})); }
  else if (key === 'progress.day_planner_start')     { progressOverlay.completeLine('guide_phase', t('progress.guide_complete')); progressOverlay.addLine('day_planner', t('progress.day_planner_starting')); }
  else if (key === 'progress.analysis_start')        { progressOverlay.completeLine('day_planner', t('progress.day_plan_complete')); progressOverlay.addLine('trip_analysis', t('progress.trip_analysis_starting')); _addAnalysisTimelineRow(); }
  else if (key === 'progress.analysis_failed')       { progressOverlay.completeLine('trip_analysis', t('progress.analysis_skipped')); _completeAnalysisTimelineRow(); }
}

function onStopResearchStarted(data) {
  const region = data.region || '';
  if      (data.section === 'activities')  progressOverlay.addLine('act_'  + data.stop_id, t('progress.activities_for_region',  {region}));
  else if (data.section === 'restaurants') progressOverlay.addLine('rest_' + data.stop_id, t('progress.restaurants_for_region', {region}));
}

function onRouteReady(data) {
  progressOverlay.completeLine('route_arch', t('progress.route_confirmed'));
  buildStopsTimeline(data.stops || []);
  if (typeof updateSidebar === 'function') updateSidebar();
}

function onActivitiesLoaded(data) {
  const { stop_id: stopId, activities = [] } = data;
  progressOverlay.completeLine('act_' + stopId, t('progress.activities_count', {count: activities.length}));
  if (stopProgress[stopId]) stopProgress[stopId].activities = true;
  const status = document.getElementById('timeline-status-' + stopId);
  if (status) {
    const actHtml = '<div class="timeline-item done"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg><span>' + t('progress.activities_loaded', {count: activities.length}) + '</span></div>';
    status.innerHTML = actHtml + (stopProgress[stopId]?.restaurants
      ? status.querySelector('.restaurants-item')?.outerHTML || ''
      : '<div class="shimmer-line short"></div>');
  }
}

function onRestaurantsLoaded(data) {
  const { stop_id: stopId, restaurants = [] } = data;
  progressOverlay.completeLine('rest_' + stopId, t('progress.restaurants_count', {count: restaurants.length}));
  if (stopProgress[stopId]) stopProgress[stopId].restaurants = true;
  const status = document.getElementById('timeline-status-' + stopId);
  if (status) {
    const restHtml = '<div class="timeline-item done restaurants-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg><span>' + t('progress.restaurants_loaded', {count: restaurants.length}) + '</span></div>';
    const shimmer = status.querySelector('.shimmer-line.short');
    if (shimmer) shimmer.remove();
    status.insertAdjacentHTML('beforeend', restHtml);
  }
}

function onStopDone(data) {
  const stopEl = document.getElementById('timeline-stop-' + data.stop_id);
  if (stopEl) stopEl.classList.add('done');
  if (typeof updateSidebar === 'function') updateSidebar();
}

function onAgentStart(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) el.textContent = data.message || t('progress.agent_starting');
}

function onAgentDone(data) {
  const el = document.getElementById('progress-agent-status');
  if (el) el.textContent = data.message || t('progress.agent_done');
}

async function onJobComplete(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressOverlay.completeLine('trip_analysis', t('progress.analysis_complete'));
  progressOverlay.completeLine('day_planner',   t('progress.day_plan_complete'));
  progressOverlay.completeLine('guide_phase',   t('progress.guide_complete'));
  progressOverlay.completeLine('route_arch',    t('progress.route_confirmed'));
  _completeAnalysisTimelineRow();
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

function onJobError(data) {
  if (progressSSE) { progressSSE.close(); progressSSE = null; }
  progressOverlay.close();
  const el = document.getElementById('progress-error');
  if (el) { el.style.display = 'block'; el.textContent = t('progress.error_prefix') + ' ' + (data.error || t('progress.unknown_error')); }
}

// ---------------------------------------------------------------------------
// SSE subscription (uses openSSE shim which delegates to SSEClient)
// ---------------------------------------------------------------------------

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
    style_mismatch_warning: function (data) {
      showToast(t('progress.style_warning') + ' ' + (data.warning || ''), 'warning');
    },
    ferry_detected: function (data) {
      const crossings = data.crossings || [];
      let msg = t('progress.ferry_detected');
      if (crossings.length > 0 && crossings[0].from && crossings[0].to)
        msg += ': ' + t('progress.ferry_crossing', { from: crossings[0].from, to: crossings[0].to });
      showToast(msg, 'info');
    },
    ping:    () => {},
    onerror: () => { console.warn('Progress SSE error'); },
  });
}
