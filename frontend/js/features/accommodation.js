'use strict';

// Accommodation — parallel accommodation loading grid; per-stop option cards and selection.
// Reads: S (state.js), Router (router.js), progressOverlay (progress.js), t (i18n.js), esc (core).
// Provides: connectAccommodationSSE, startAccommodationPhase, buildAllStopPanels, startPlanningWithAllSelections.

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

let accSSE = null;
let allStopPanels = {};  // stop_id → {stop, options}

// ---------------------------------------------------------------------------
// SSE connection
// ---------------------------------------------------------------------------

/** Opens the accommodation SSE stream and returns a promise that resolves once the connection is open. */
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

// ---------------------------------------------------------------------------
// Phase initialisation
// ---------------------------------------------------------------------------

/** Initialises the accommodation phase: resets state, renders budget info, and builds all stop panels. */
function startAccommodationPhase(data) {
  S.allStops = data.selected_stops || [];
  if (typeof updateSidebar === 'function') updateSidebar();
  S.pendingSelections = {};
  S.accSelectionCount = 0;
  allStopPanels = {};

  const budgetState = data.budget_state || {};
  renderBudgetState(budgetState);

  buildAllStopPanels(S.allStops);

  const btn = document.getElementById('start-planning-btn');
  if (btn) btn.disabled = true;
}

/** Renders skeleton panels for every stop in the accommodation grid. */
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
          <span class="acc-nights">${stop.nights !== 1 ? t('accommodation.night_plural', {nights: stop.nights}) : t('accommodation.night_singular', {nights: stop.nights})}</span>
        </div>
        <div class="acc-options-grid" id="acc-options-${stop.id}">
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
          <div class="shimmer-card"></div>
        </div>
        <div class="acc-resarch-row" id="acc-resarch-row-${stop.id}">
          <input class="acc-resarch-input" id="acc-resarch-input-${stop.id}"
                 placeholder="${t('accommodation.research_placeholder')}" />
          <button class="btn btn-secondary acc-resarch-btn"
                  onclick="researchAccommodation(${stop.id})">${t('accommodation.research_btn')}</button>
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
  progressOverlay.addLine('acc_' + stopId, t('accommodation.searching_options', {region: data.region || ''}));
}

function renderAccCards(stopId, options, mustHaves) {
  const mh = mustHaves || (S.allStops.find(s => s.id == stopId) ? [] : []);
  return options.map((opt, i) => {
    const selectedClass = S.pendingSelections[stopId] === i ? 'selected' : '';
    const starCount = opt.rating ? Math.round(opt.rating / 2) : 0;
    const stars = starCount > 0
      ? Array.from({length: starCount}, () => `<svg viewBox="0 0 24 24" width="13" height="13" style="fill:#f5a623;stroke:none;vertical-align:-1px" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`).join('')
      : '';
    const features = (opt.features || []).map(f => {
      const isMH = (opt.matched_must_haves || []).some(m => m.toLowerCase() === f.toLowerCase());
      return `<span class="feature-tag${isMH ? ' must-have' : ''}">${esc(f)}</span>`;
    }).slice(0, 5).join('');
    const imgHtml = buildHeroPhotoLoading('md');
    const isGeheimtipp = opt.is_geheimtipp === true;
    const cardClass = isGeheimtipp ? 'acc-option-card acc-geheimtipp-card' : 'acc-option-card';
    const geheimtippBadge = isGeheimtipp
      ? `<span class="geheimtipp-badge">${t('accommodation.geheimtipp_badge')}</span>`
      : '';
    const descHtml = opt.description
      ? `<div class="acc-description">${highlightMustHaves(opt.description, opt.matched_must_haves || [])}</div>`
      : '';
    const geheimtippHint = (isGeheimtipp && opt.geheimtipp_hinweis)
      ? `<div class="acc-geheimtipp-hint">${esc(opt.geheimtipp_hinweis)}</div>`
      : '';

    // Booking links
    const bookingDeepLink = (!isGeheimtipp && opt.booking_url)
      ? `<a class="acc-booking-link" href="${safeUrl(opt.booking_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${t('accommodation.booking_view')} <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>`
      : '';
    const bookingSearchLink = (isGeheimtipp && opt.booking_search_url)
      ? `<a class="acc-booking-link acc-booking-search" href="${safeUrl(opt.booking_search_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${t('accommodation.booking_search')} <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>`
      : '';
    const websiteLink = opt.hotel_website_url
      ? `<a class="acc-website-link" href="${safeUrl(opt.hotel_website_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${t('accommodation.hotel_website')} <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>`
      : '';

    return `
      <div class="${cardClass} ${selectedClass}" onclick="selectAccommodationInPanel(${stopId}, ${i})"
           data-stop="${stopId}" data-idx="${i}">
        ${imgHtml}
        <div class="acc-card-body">
          ${geheimtippBadge}
          <h4>${esc(opt.name)}</h4>
          <div class="acc-type-badge">${esc(opt.type)}</div>
          ${stars ? `<div class="acc-stars">${stars}</div>` : ''}
          <div class="acc-price">
            <strong>ca. CHF ${(opt.price_per_night_chf || 0).toLocaleString('de-CH')}</strong>
            <span>${t('accommodation.per_night')}</span>
          </div>
          <div class="acc-total">${t('accommodation.total_label')} ${(opt.total_price_chf || 0).toLocaleString('de-CH')}</div>
          <p class="acc-teaser">${esc(opt.teaser)}</p>
          ${descHtml}
          <div class="acc-features">${features}</div>
          ${geheimtippHint}
          <div class="acc-links-row">
            ${bookingDeepLink}${bookingSearchLink}${websiteLink}
          </div>
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

  // Lazy-load images for each card
  requestAnimationFrame(() => {
    grid.querySelectorAll('.acc-option-card').forEach((card, i) => {
      const opt = options[i];
      if (opt && typeof _lazyLoadEntityImages === 'function') {
        _lazyLoadEntityImages(card, opt.name, stop.lat, stop.lng, 'hotel');
      }
    });
  });

  const count = options.length;
  progressOverlay.completeLine('acc_' + stopId, t('accommodation.options_found', {count}));
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
  if (typeof updateSidebar === 'function') updateSidebar();

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
      <span>${t('accommodation.budget_label', {pct: 45})}</span>
      <strong>CHF ${(bs.accommodation_budget_chf || 0).toLocaleString('de-CH')}</strong>
    </div>
    <div class="budget-info-row">
      <span>${t('accommodation.spent_label')}</span>
      <strong id="acc-budget-spent">CHF 0</strong>
    </div>
    <div class="budget-info-row">
      <span>${t('accommodation.total_budget_label')}</span>
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
      requestAnimationFrame(() => {
        grid.querySelectorAll('.acc-option-card').forEach((card, i) => {
          const opt = options[i];
          if (opt && typeof _lazyLoadEntityImages === 'function') {
            _lazyLoadEntityImages(card, opt.name, stop.lat, stop.lng, 'hotel');
          }
        });
      });
    }

    updateBudgetFromSelections();

    const btn = document.getElementById('start-planning-btn');
    if (btn) {
      btn.disabled = S.accSelectionCount < S.allStops.length;
    }
  } catch (err) {
    if (grid) {
      grid.innerHTML = `<div class="acc-error">${esc(t('accommodation.search_error'))} ${esc(err.message)}</div>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Planning submission
// ---------------------------------------------------------------------------

/** Confirms all accommodation selections with the backend and starts the full planning pipeline. */
async function startPlanningWithAllSelections() {
  const btn = document.getElementById('start-planning-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('accommodation.starting_planning'); }

  // Close accommodation SSE
  if (accSSE) { accSSE.close(); accSSE = null; }

  try {
    // Convert pendingSelections keys to strings for API
    const selections = {};
    for (const [stopId, idx] of Object.entries(S.pendingSelections)) {
      selections[String(stopId)] = idx;
    }

    // Show progress overlay immediately — no loading screen
    progressOverlay.open(t('api.creating_travel_plan'));
    showSection('progress');
    Router.navigate('/progress/' + S.jobId);

    // Step 1: confirm accommodations (quiet — no loading overlay)
    progressOverlay.addLine('confirm_acc', t('accommodation.confirming'));
    await apiConfirmAccommodationsQuiet(S.jobId, selections);
    progressOverlay.completeLine('confirm_acc', t('accommodation.confirmed'));

    // Step 2: start planning (quiet — no loading overlay)
    progressOverlay.addLine('start_plan', t('accommodation.planning_starting'));
    await apiStartPlanningQuiet(S.jobId);
    progressOverlay.completeLine('start_plan', t('accommodation.started'));

    // Step 3: connect SSE for remaining progress
    connectSSE(S.jobId);

  } catch (err) {
    progressOverlay.close();
    alert(t('accommodation.planning_error') + ' ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = t('accommodation.start_planning'); }
  }
}

function redoRoute() {
  lsClear(LS_ROUTE);
  lsClear(LS_ACCOMMODATIONS);
  S.selectedStops = [];
  S.jobId = null;
  Router.navigate('/');
}
