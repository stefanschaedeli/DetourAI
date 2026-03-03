'use strict';

let accSSE = null;
let allStopPanels = {};  // stop_id → {stop, options}

function connectAccommodationSSE(jobId) {
  if (accSSE) { accSSE.close(); accSSE = null; }

  accSSE = openSSE(jobId, {
    accommodation_loading:      onAccommodationLoading,
    accommodation_loaded:       onAccommodationLoaded,
    accommodations_all_loaded:  onAccommodationsAllLoaded,
    debug_log:                  onAccDebugLog,
    onerror: () => {
      console.warn('Accommodation SSE error');
    },
  });

  // Return a promise that resolves once the EventSource connection is open
  return new Promise(resolve => {
    accSSE.addEventListener('open', resolve, { once: true });
    // Fallback: resolve after 500ms even if open event never fires
    setTimeout(resolve, 500);
  });
}

function onAccDebugLog(data) {
  S.logs.push(data);
  updateDebugLog();
}

function startAccommodationPhase(data) {
  S.allStops = data.selected_stops || [];
  S.pendingSelections = {};
  S.accSelectionCount = 0;
  allStopPanels = {};

  const budgetState = data.budget_state || {};
  renderBudgetState(budgetState);

  buildAllStopPanels(S.allStops);

  const btn = document.getElementById('start-planning-btn');
  if (btn) btn.disabled = true;
}

function buildAllStopPanels(stops) {
  const container = document.getElementById('accommodation-stops-container');
  if (!container) return;

  container.innerHTML = stops.map(stop => {
    const flag = FLAGS[stop.country] || '';
    return `
      <div class="acc-stop-panel" id="acc-panel-${stop.id}">
        <div class="acc-stop-header">
          <span class="acc-stop-num">${stop.id}</span>
          <h3>${flag} ${esc(stop.region)}</h3>
          <span class="acc-nights">${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}</span>
        </div>
        <div class="acc-options-grid" id="acc-options-${stop.id}">
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
        </div>
      </div>
    `;
  }).join('');
}

function onAccommodationLoading(data) {
  const stopId = data.stop_id;
  const panel = document.getElementById(`acc-panel-${stopId}`);
  if (!panel) return;
  const grid = panel.querySelector('.acc-options-grid');
  if (grid) {
    grid.innerHTML = '<div class="shimmer-card"></div><div class="shimmer-card"></div><div class="shimmer-card"></div><div class="shimmer-card"></div>';
  }
}

function optTypeLabel(type) {
  const labels = { budget: 'Budget', comfort: 'Komfort', premium: 'Premium', geheimtipp: 'Geheimtipp' };
  return labels[type] || esc(type);
}

function onAccommodationLoaded(data) {
  const stopId = data.stop_id;
  const options = data.options || [];
  const stop    = data.stop || {};

  allStopPanels[stopId] = { stop, options };

  const grid = document.getElementById(`acc-options-${stopId}`);
  if (!grid) return;

  grid.innerHTML = options.map((opt, i) => {
    const selectedClass = S.pendingSelections[stopId] === i ? 'selected' : '';
    const stars = opt.rating ? '★'.repeat(Math.round(opt.rating / 2)) : '';
    const features = (opt.features || []).slice(0, 4).map(f => `<span class="feature-tag">${esc(f)}</span>`).join('');
    const imgHtml = buildImageGallery(
      opt.image_overview, opt.image_mood, opt.image_customer, esc(opt.name)
    );
    const isGeheimtipp = opt.option_type === 'geheimtipp';
    const cardClass = isGeheimtipp ? 'acc-option-card acc-geheimtipp-card' : 'acc-option-card';
    const bookingBtn = (!isGeheimtipp && opt.booking_url)
      ? `<a class="acc-booking-link" href="${esc(opt.booking_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Bei Booking.com anschauen →</a>`
      : '';
    const geheimtippHint = (isGeheimtipp && opt.geheimtipp_hinweis)
      ? `<div class="acc-geheimtipp-hint">${esc(opt.geheimtipp_hinweis)}</div>`
      : '';
    const isRealPrice = opt.price_source === 'booking.com';
    const priceLabel = isRealPrice
      ? `CHF ${(opt.price_per_night_chf || 0).toLocaleString('de-CH')}`
      : `ca. CHF ${(opt.price_per_night_chf || 0).toLocaleString('de-CH')}`;
    const priceNote = isRealPrice
      ? `<span class="price-source real">Booking.com-Preis</span>`
      : `<span class="price-source estimate">Schätzung</span>`;
    return `
      <div class="${cardClass} ${selectedClass}" onclick="selectAccommodationInPanel(${stopId}, ${i})"
           data-stop="${stopId}" data-idx="${i}">
        ${imgHtml}
        <div class="acc-option-type type-${esc(opt.option_type)}">${optTypeLabel(opt.option_type)}</div>
        <h4>${esc(opt.name)}</h4>
        <div class="acc-type-badge">${esc(opt.type)}</div>
        ${stars ? `<div class="acc-stars">${stars}</div>` : ''}
        <div class="acc-price">
          <strong>${priceLabel}</strong>
          <span>/Nacht</span>
        </div>
        ${priceNote}
        <div class="acc-total">Total: CHF ${(opt.total_price_chf || 0).toLocaleString('de-CH')}</div>
        <p class="acc-teaser">${esc(opt.teaser)}</p>
        <div class="acc-features">${features}</div>
        ${geheimtippHint}
        ${bookingBtn}
      </div>
    `;
  }).join('');
}

function onAccommodationsAllLoaded(data) {
  S.allAccLoaded = true;
  const btn = document.getElementById('start-planning-btn');
  if (btn) {
    btn.disabled = Object.keys(S.pendingSelections).length < S.allStops.length;
  }
  updateBudgetFromSelections();
}

function selectAccommodationInPanel(stopId, optionIdx) {
  // Deselect others in same panel
  const grid = document.getElementById(`acc-options-${stopId}`);
  if (!grid) return;
  grid.querySelectorAll('.acc-option-card').forEach((card, i) => {
    card.classList.toggle('selected', i === optionIdx);
  });

  S.pendingSelections[stopId] = optionIdx;
  S.accSelectionCount = Object.keys(S.pendingSelections).length;

  lsSet(LS_ACCOMMODATIONS, {
    jobId: S.jobId,
    allStops: S.allStops,
    prefetchedOptions: allStopPanels,
    pendingSelections: S.pendingSelections,
  });

  updateBudgetFromSelections();

  // Enable planning button when all stops have a selection
  const btn = document.getElementById('start-planning-btn');
  if (btn) {
    btn.disabled = S.accSelectionCount < S.allStops.length;
  }
}

function updateBudgetFromSelections() {
  let spent = 0;
  for (const [stopId, idx] of Object.entries(S.pendingSelections)) {
    const panel = allStopPanels[stopId];
    if (panel && panel.options[idx]) {
      spent += panel.options[idx].total_price_chf || 0;
    }
  }
  const budgetEl = document.getElementById('acc-budget-spent');
  if (budgetEl) budgetEl.textContent = `CHF ${spent.toLocaleString('de-CH')}`;
}

function renderBudgetState(bs) {
  const el = document.getElementById('acc-budget-info');
  if (!el || !bs) return;
  el.innerHTML = `
    <div class="budget-info-row">
      <span>Unterkunftsbudget (45%)</span>
      <strong>CHF ${(bs.accommodation_budget_chf || 0).toLocaleString('de-CH')}</strong>
    </div>
    <div class="budget-info-row">
      <span>Ausgegeben</span>
      <strong id="acc-budget-spent">CHF 0</strong>
    </div>
    <div class="budget-info-row">
      <span>Gesamtbudget</span>
      <strong>CHF ${(bs.total_budget_chf || 0).toLocaleString('de-CH')}</strong>
    </div>
  `;
}

async function startPlanningWithAllSelections() {
  const btn = document.getElementById('start-planning-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Starte Planung…'; }

  // Close accommodation SSE
  if (accSSE) { accSSE.close(); accSSE = null; }

  try {
    // Convert pendingSelections keys to strings for API
    const selections = {};
    for (const [stopId, idx] of Object.entries(S.pendingSelections)) {
      selections[String(stopId)] = idx;
    }

    await apiConfirmAccommodations(S.jobId, selections);
    await apiStartPlanning(S.jobId);

    showSection('progress');
    connectSSE(S.jobId);

  } catch (err) {
    alert('Fehler beim Starten der Planung: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Planung starten'; }
  }
}

function redoRoute() {
  lsClear(LS_ROUTE);
  lsClear(LS_ACCOMMODATIONS);
  S.selectedStops = [];
  S.jobId = null;
  showSection('form-section');
}
