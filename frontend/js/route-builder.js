'use strict';

let routeMeta = {};

function startRouteBuilding(data) {
  S.selectedStops = [];
  routeMeta = data.meta || {};
  renderOptions(data.options || [], data.meta || {});
}

function renderOptions(options, meta) {
  routeMeta = meta || routeMeta;
  S.currentOptions = options;
  S.loadingOptions = false;

  const container = document.getElementById('route-options-container');
  const status    = document.getElementById('route-status');
  const confirmBtn = document.getElementById('confirm-route-btn');

  if (!container) return;

  // Status header
  const stopNum = (meta.stop_number || 1);
  const daysRem = (meta.days_remaining || 0);
  const target  = meta.segment_target || '';
  const segInfo = meta.segment_count > 1
    ? ` (Segment ${(meta.segment_index || 0) + 1}/${meta.segment_count} → ${esc(target)})`
    : ` → ${esc(target)}`;

  status.innerHTML = `
    <div class="route-status-info">
      <strong>Stop #${stopNum}</strong>${segInfo}
      <span class="badge">${daysRem} Tage verbleibend</span>
    </div>
  `;

  // Stops built so far
  renderBuiltStops();

  // Options cards
  if (options.length === 0 && meta.route_could_be_complete) {
    container.innerHTML = `
      <div class="route-complete-msg">
        <p>Die Route kann jetzt abgeschlossen werden.</p>
        <button class="btn btn-primary" onclick="confirmRoute()">Route bestätigen</button>
      </div>
    `;
    if (confirmBtn) confirmBtn.style.display = 'none';
    return;
  }

  container.innerHTML = options.map((opt, i) => {
    const flag = FLAGS[opt.country] || '';
    const driveKm = opt.drive_km ? ` · ${opt.drive_km} km` : '';
    return `
      <div class="option-card" onclick="selectOption(${i})">
        <div class="option-type-badge type-${esc(opt.option_type)}">${esc(opt.option_type)}</div>
        <h3>${flag} ${esc(opt.region)}, ${esc(opt.country)}</h3>
        <div class="option-meta">
          <span>${opt.drive_hours}h Fahrt${driveKm}</span>
          <span>${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}</span>
        </div>
        <p class="option-teaser">${esc(opt.teaser)}</p>
        <ul class="option-highlights">
          ${(opt.highlights || []).map(h => `<li>${esc(h)}</li>`).join('')}
        </ul>
      </div>
    `;
  }).join('');

  // Show confirm button if route could be complete
  if (confirmBtn) {
    confirmBtn.style.display = meta.route_could_be_complete ? 'block' : 'none';
  }
}

function renderBuiltStops() {
  const list = document.getElementById('built-stops-list');
  if (!list) return;
  list.innerHTML = S.selectedStops.map((stop, i) => {
    const flag = FLAGS[stop.country] || '';
    return `
      <div class="built-stop">
        <div class="built-stop-number">${i + 1}</div>
        <div class="built-stop-info">
          <strong>${flag} ${esc(stop.region)}</strong>
          <span>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''} · ${stop.drive_hours || stop.drive_hours_from_prev || 0}h Fahrt</span>
        </div>
      </div>
    `;
  }).join('');
}

async function selectOption(idx) {
  if (S.loadingOptions) return;
  S.loadingOptions = true;

  const cards = document.querySelectorAll('.option-card');
  cards.forEach((c, i) => c.classList.toggle('selected', i === idx));

  const container = document.getElementById('route-options-container');
  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Nächste Optionen werden geladen…</p></div>';

  try {
    const data = await apiSelectStop(S.jobId, idx);

    addBuiltStop(data.selected_stop);

    // Via-point was auto-added?
    if (data.via_point_added) {
      addBuiltStop(data.via_point_added);
    }

    saveRouteState();

    const options = data.options || [];
    const meta    = data.meta || {};

    if (options.length === 0 && meta.route_could_be_complete) {
      // Route done — show confirm
      renderOptions([], meta);
    } else if (options.length > 0) {
      renderOptions(options, meta);
    } else {
      // Unexpected: show confirm
      renderOptions([], meta);
    }

  } catch (err) {
    container.innerHTML = `<div class="error-msg">Fehler: ${esc(err.message)}</div>`;
    S.loadingOptions = false;
  }
}

function addBuiltStop(stop) {
  if (!stop) return;
  S.selectedStops.push(stop);
}

async function confirmRoute() {
  const btn = document.getElementById('confirm-route-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Bestätige…'; }
  S.confirmingRoute = true;

  try {
    const data = await apiConfirmRoute(S.jobId);
    S.allStops = data.selected_stops || [];

    // Show accommodation section and connect SSE BEFORE firing the prefetch,
    // so no accommodation_loaded events are missed.
    showSection('accommodation');
    startAccommodationPhase(data);

    // Wait for the EventSource connection to be established before triggering
    // the prefetch task — otherwise early SSE events may be lost.
    await connectAccommodationSSE(S.jobId);

    // Now trigger the prefetch — events will be received by the open SSE
    await apiStartAccommodations(S.jobId);

  } catch (err) {
    alert('Fehler beim Bestätigen der Route: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Route bestätigen'; }
    S.confirmingRoute = false;
  }
}

function backToForm() {
  showSection('form-section');
}

function saveRouteState() {
  const stopsObj = {};
  const stopsOrder = [];
  S.selectedStops.forEach(s => {
    stopsObj[s.id] = s;
    stopsOrder.push(s.id);
  });
  lsSet(LS_ROUTE, { jobId: S.jobId, stops: stopsObj, stopsOrder });
}

function searchNextStop() {
  // Manual trigger if needed
  if (S.currentOptions.length > 0) {
    renderOptions(S.currentOptions, routeMeta);
  }
}
