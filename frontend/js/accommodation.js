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
        <div class="acc-resarch-row" id="acc-resarch-row-${stop.id}">
          <input class="acc-resarch-input" id="acc-resarch-input-${stop.id}"
                 placeholder="z.B. ruhiger am See, mit Sauna…" />
          <button class="btn btn-secondary acc-resarch-btn"
                  onclick="researchAccommodation(${stop.id})">Neu suchen</button>
        </div>
      </div>
    `;
  }).join('');
}

function onAccommodationLoading(data) {
  const stopId = data.stop_id;
  const grid = document.getElementById(`acc-options-${stopId}`);
  if (grid) {
    grid.innerHTML = '<div class="shimmer-card"></div><div class="shimmer-card"></div><div class="shimmer-card"></div>';
  }
  progressOverlay.addLine('acc_' + stopId, `Suche Unterkunftsoptionen für ${esc(data.region || '')}…`);
}

function renderAccCards(stopId, options, mustHaves) {
  const mh = mustHaves || (S.allStops.find(s => s.id == stopId) ? [] : []);
  return options.map((opt, i) => {
    const selectedClass = S.pendingSelections[stopId] === i ? 'selected' : '';
    const stars = opt.rating ? '★'.repeat(Math.round(opt.rating / 2)) : '';
    const features = (opt.features || []).map(f => {
      const isMH = (opt.matched_must_haves || []).some(m => m.toLowerCase() === f.toLowerCase());
      return `<span class="feature-tag${isMH ? ' must-have' : ''}">${esc(f)}</span>`;
    }).slice(0, 5).join('');
    const imgHtml = buildImageGallery(
      opt.image_overview, opt.image_mood, opt.image_customer, esc(opt.name)
    );
    const isGeheimtipp = opt.is_geheimtipp === true;
    const cardClass = isGeheimtipp ? 'acc-option-card acc-geheimtipp-card' : 'acc-option-card';
    const geheimtippBadge = isGeheimtipp
      ? `<span class="geheimtipp-badge">Geheimtipp</span>`
      : '';
    const descHtml = opt.description
      ? `<div class="acc-description">${highlightMustHaves(opt.description, opt.matched_must_haves || [])}</div>`
      : '';
    const geheimtippHint = (isGeheimtipp && opt.geheimtipp_hinweis)
      ? `<div class="acc-geheimtipp-hint">${esc(opt.geheimtipp_hinweis)}</div>`
      : '';

    // Booking links
    const bookingDeepLink = (!isGeheimtipp && opt.booking_url)
      ? `<a class="acc-booking-link" href="${safeUrl(opt.booking_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Bei Booking.com anschauen →</a>`
      : '';
    const bookingSearchLink = (isGeheimtipp && opt.booking_search_url)
      ? `<a class="acc-booking-link acc-booking-search" href="${safeUrl(opt.booking_search_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Bei Booking.com suchen →</a>`
      : '';
    const websiteLink = opt.hotel_website_url
      ? `<a class="acc-website-link" href="${safeUrl(opt.hotel_website_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Hotelwebseite →</a>`
      : '';

    return `
      <div class="${cardClass} ${selectedClass}" onclick="selectAccommodationInPanel(${stopId}, ${i})"
           data-stop="${stopId}" data-idx="${i}">
        ${imgHtml}
        ${geheimtippBadge}
        <h4>${esc(opt.name)}</h4>
        <div class="acc-type-badge">${esc(opt.type)}</div>
        ${stars ? `<div class="acc-stars">${stars}</div>` : ''}
        <div class="acc-price">
          <strong>ca. CHF ${(opt.price_per_night_chf || 0).toLocaleString('de-CH')}</strong>
          <span>/Nacht</span>
        </div>
        <div class="acc-total">Total: ca. CHF ${(opt.total_price_chf || 0).toLocaleString('de-CH')}</div>
        <p class="acc-teaser">${esc(opt.teaser)}</p>
        ${descHtml}
        <div class="acc-features">${features}</div>
        ${geheimtippHint}
        <div class="acc-links-row">
          ${bookingDeepLink}${bookingSearchLink}${websiteLink}
        </div>
      </div>
    `;
  }).join('');
}

function onAccommodationLoaded(data) {
  const stopId = data.stop_id;
  const options = data.options || [];
  const stop    = data.stop || {};

  allStopPanels[stopId] = { stop, options };

  const grid = document.getElementById(`acc-options-${stopId}`);
  if (!grid) return;

  grid.innerHTML = renderAccCards(stopId, options, []);

  const count = options.length;
  progressOverlay.completeLine('acc_' + stopId, `${count} Optionen gefunden`);
}

function onAccommodationsAllLoaded(data) {
  S.allAccLoaded = true;
  const btn = document.getElementById('start-planning-btn');
  if (btn) {
    btn.disabled = Object.keys(S.pendingSelections).length < S.allStops.length;
  }
  updateBudgetFromSelections();
  progressOverlay.close();
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

async function researchAccommodation(stopId) {
  const input = document.getElementById(`acc-resarch-input-${stopId}`);
  const extraInstructions = input ? input.value.trim() : '';

  const grid = document.getElementById(`acc-options-${stopId}`);
  if (grid) {
    grid.innerHTML = '<div class="shimmer-card"></div><div class="shimmer-card"></div><div class="shimmer-card"></div>';
  }

  try {
    const result = await apiResearchAccommodation(S.jobId, stopId, extraInstructions);
    const options = result.options || [];
    const stop = result.stop || {};

    allStopPanels[stopId] = { stop, options };

    // Clear selection for this stop
    delete S.pendingSelections[stopId];
    S.accSelectionCount = Object.keys(S.pendingSelections).length;

    if (grid) {
      grid.innerHTML = renderAccCards(stopId, options, []);
    }

    updateBudgetFromSelections();

    const btn = document.getElementById('start-planning-btn');
    if (btn) {
      btn.disabled = S.accSelectionCount < S.allStops.length;
    }
  } catch (err) {
    if (grid) {
      grid.innerHTML = `<div class="acc-error">Fehler bei der Suche: ${esc(err.message)}</div>`;
    }
  }
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

    progressOverlay.open('Reiseplan wird erstellt…');
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
