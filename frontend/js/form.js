'use strict';

let viaPoints = [];  // [{location, hasDate, date, notes}]

function initForm() {
  renderViaPoints();
  initTravelStyles();
  initSliders();
  initBudgetSliders();
  setupFormAutoSave();
  restoreFormFromCache();
  checkResume();
  updateQuickSubmitBar();

  // Close settings menu on click outside
  document.addEventListener('click', e => {
    if (!e.target.closest('.header-settings')) {
      const m = document.getElementById('settings-menu');
      if (m) m.style.display = 'none';
    }
  });
}

// ---------------------------------------------------------------------------
// Step navigation
// ---------------------------------------------------------------------------

function goToStep(n) {
  S.step = n;
  document.querySelectorAll('.form-step').forEach((el, i) => {
    el.classList.toggle('active', i + 1 === n);
  });
  document.querySelectorAll('.step-indicator .step').forEach((el, i) => {
    el.classList.toggle('active', i + 1 === n);
    el.classList.toggle('done', i + 1 < n);
  });
  window.scrollTo(0, 0);
}

function nextStep() {
  if (!validateStep(S.step)) return;
  if (S.step < 6) {
    if (S.step === 5) renderSummary();
    goToStep(S.step + 1);
  }
}

function prevStep() {
  if (S.step > 1) goToStep(S.step - 1);
}

function validateStep(n) {
  if (n === 1) {
    const start = document.getElementById('start-location').value.trim();
    const dest  = document.getElementById('main-destination').value.trim();
    const sd    = document.getElementById('start-date').value;
    const ed    = document.getElementById('end-date').value;
    if (!start) { alert('Bitte Startort eingeben.'); return false; }
    if (!dest)  { alert('Bitte Hauptziel eingeben.'); return false; }
    if (!sd || !ed) { alert('Bitte Reisedaten eingeben.'); return false; }
    if (sd >= ed) { alert('Enddatum muss nach Startdatum liegen.'); return false; }
  }
  if (n === 5) {
    const acc  = parseInt(document.getElementById('budget-acc-pct')?.value)  || 0;
    const food = parseInt(document.getElementById('budget-food-pct')?.value) || 0;
    const act  = parseInt(document.getElementById('budget-act-pct')?.value)  || 0;
    if (acc + food + act !== 100) {
      alert('Die Budgetaufteilung muss zusammen 100% ergeben.');
      return false;
    }
  }
  return true;
}

// ---------------------------------------------------------------------------
// Settings menu
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Quick-submit sticky bar
// ---------------------------------------------------------------------------

function updateQuickSubmitBar() {
  const bar = document.getElementById('quick-submit-bar');
  if (!bar) return;
  // Show only when form-section is active and step 1 required fields are filled
  const formActive = document.getElementById('form-section')?.classList.contains('active');
  const start = document.getElementById('start-location')?.value.trim();
  const dest  = document.getElementById('main-destination')?.value.trim();
  const sd    = document.getElementById('start-date')?.value;
  const ed    = document.getElementById('end-date')?.value;
  const ready = formActive && start && dest && sd && ed && sd < ed;
  bar.classList.toggle('visible', !!ready);
}

async function quickSubmitTrip() {
  // Validate step 1 (required fields) — skip steps 2-6 validation
  const start = document.getElementById('start-location')?.value.trim();
  const dest  = document.getElementById('main-destination')?.value.trim();
  const sd    = document.getElementById('start-date')?.value;
  const ed    = document.getElementById('end-date')?.value;
  if (!start) { alert('Bitte Startort eingeben.'); return; }
  if (!dest)  { alert('Bitte Hauptziel eingeben.'); return; }
  if (!sd || !ed) { alert('Bitte Reisedaten eingeben.'); return; }
  if (sd >= ed)   { alert('Enddatum muss nach Startdatum liegen.'); return; }
  await submitTrip();
}

function toggleSettings() {
  const menu = document.getElementById('settings-menu');
  if (!menu) return;
  const open = menu.style.display !== 'none';
  menu.style.display = open ? 'none' : 'block';
}

// ---------------------------------------------------------------------------
// Via-points
// ---------------------------------------------------------------------------

function addViaPoint() {
  viaPoints.push({ location: '', hasDate: false, date: '', notes: '' });
  renderViaPoints();
}

function removeViaPoint(idx) {
  viaPoints.splice(idx, 1);
  renderViaPoints();
}

function toggleViaDate(idx) {
  viaPoints[idx].hasDate = !viaPoints[idx].hasDate;
  renderViaPoints();
}

function renderViaPoints() {
  const container = document.getElementById('via-points-list');
  if (!container) return;
  container.innerHTML = viaPoints.map((vp, i) => `
    <div class="via-point">
      <div class="via-point-row">
        <input type="text" placeholder="Ort (z.B. Annecy)" value="${esc(vp.location)}"
          oninput="viaPoints[${i}].location = this.value; saveFormToCache()">
        <button class="btn-icon" onclick="toggleViaDate(${i})" title="Datum festlegen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/>
            <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
        </button>
        <button class="btn-icon btn-danger" onclick="removeViaPoint(${i})" title="Entfernen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
          </svg>
        </button>
      </div>
      ${vp.hasDate ? `<input type="date" value="${esc(vp.date)}"
        oninput="viaPoints[${i}].date = this.value; saveFormToCache()">` : ''}
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Travel styles
// ---------------------------------------------------------------------------

function initTravelStyles() {
  const grid = document.getElementById('travel-style-grid');
  if (!grid) return;
  grid.innerHTML = TRAVEL_STYLES.map(style => `
    <div class="style-card" data-id="${esc(style.id)}" onclick="toggleStyle(this)">
      <div class="style-icon">${style.icon}</div>
      <div class="style-label">${esc(style.label)}</div>
    </div>
  `).join('');
}

function toggleStyle(card) {
  const id = card.dataset.id;
  card.classList.toggle('selected');
  if (card.classList.contains('selected')) {
    if (!S.travelStyles.includes(id)) S.travelStyles.push(id);
  } else {
    S.travelStyles = S.travelStyles.filter(s => s !== id);
  }
  saveFormToCache();
}

// ---------------------------------------------------------------------------
// Tag input (mandatory activities)
// ---------------------------------------------------------------------------

function addTagFromInput() {
  const input = document.getElementById('mandatory-tag-input');
  if (!input) return;
  const val = input.value.trim();
  if (val && !S.mandatoryTags.includes(val)) {
    S.mandatoryTags.push(val);
    renderTags();
    input.value = '';
    saveFormToCache();
  }
}

function removeTag(name) {
  S.mandatoryTags = S.mandatoryTags.filter(t => t !== name);
  renderTags();
  saveFormToCache();
}

function renderTags() {
  const container = document.getElementById('mandatory-tags');
  if (!container) return;
  container.innerHTML = S.mandatoryTags.map(tag => `
    <span class="tag">
      ${esc(tag)}
      <button onclick="removeTag(${JSON.stringify(tag)})" title="Entfernen">×</button>
    </span>
  `).join('');
}

// ---------------------------------------------------------------------------
// Children
// ---------------------------------------------------------------------------

function addChild() {
  S.children.push({ age: 5 });
  renderChildren();
}

function removeChild(idx) {
  S.children.splice(idx, 1);
  renderChildren();
}

function renderChildren() {
  const list = document.getElementById('children-list');
  if (!list) return;
  list.innerHTML = S.children.map((child, i) => `
    <div class="child-row">
      <label>Kind ${i + 1}, Alter:</label>
      <input type="number" min="0" max="17" value="${child.age}"
        oninput="S.children[${i}].age = parseInt(this.value) || 0; saveFormToCache()">
      <button class="btn-icon btn-danger" onclick="removeChild(${i})">×</button>
    </div>
  `).join('');
  document.getElementById('adults-count').textContent = S.adults;
}

function changeAdults(delta) {
  S.adults = Math.max(1, Math.min(12, S.adults + delta));
  document.getElementById('adults-count').textContent = S.adults;
  saveFormToCache();
}

// ---------------------------------------------------------------------------
// Accommodation styles + must-haves
// ---------------------------------------------------------------------------

function toggleAccStyle(el) {
  el.classList.toggle('selected');
}

function toggleMustHave(el) {
  el.classList.toggle('selected');
}

function getSelectedAccStyles() {
  return Array.from(document.querySelectorAll('.acc-style.selected')).map(el => el.dataset.id);
}

function getSelectedMustHaves() {
  return Array.from(document.querySelectorAll('.must-have.selected')).map(el => el.dataset.id);
}

// ---------------------------------------------------------------------------
// Sliders
// ---------------------------------------------------------------------------

function initSliders() {
  ['hotel-radius', 'activities-radius', 'max-drive-hours'].forEach(id => {
    const slider = document.getElementById(id);
    const display = document.getElementById(id + '-display');
    if (slider && display) {
      slider.oninput = () => { display.textContent = slider.value; saveFormToCache(); };
    }
  });
}

// ---------------------------------------------------------------------------
// Budget sliders
// ---------------------------------------------------------------------------

function initBudgetSliders() {
  ['budget-acc-pct', 'budget-food-pct', 'budget-act-pct'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.oninput = () => { updateBudgetPreview(); saveFormToCache(); };
  });
  const budgetInput = document.getElementById('budget-chf');
  if (budgetInput) budgetInput.oninput = () => { updateBudgetPreview(); saveFormToCache(); };
  updateBudgetPreview();
}

function updateBudgetPreview() {
  const acc  = parseInt(document.getElementById('budget-acc-pct')?.value)  || 60;
  const food = parseInt(document.getElementById('budget-food-pct')?.value) || 20;
  const act  = parseInt(document.getElementById('budget-act-pct')?.value)  || 20;
  const sum  = acc + food + act;
  const total = parseFloat(document.getElementById('budget-chf')?.value) || 3000;

  const sumEl   = document.getElementById('budget-pct-sum');
  const checkEl = document.getElementById('budget-total-check');
  if (sumEl) sumEl.textContent = sum;
  if (checkEl) {
    checkEl.classList.toggle('invalid', sum !== 100);
    // Replace the text node after the <strong>
    const strong = checkEl.querySelector('strong');
    if (strong && strong.nextSibling) {
      strong.nextSibling.textContent = sum === 100 ? '% ✓' : '% ✗ (muss 100% sein)';
    }
  }

  const fmt = v => Math.round(total * v / 100).toLocaleString('de-CH');
  const el  = id => document.getElementById(id);
  if (el('budget-acc-pct-display'))  el('budget-acc-pct-display').textContent  = acc;
  if (el('budget-food-pct-display')) el('budget-food-pct-display').textContent = food;
  if (el('budget-act-pct-display'))  el('budget-act-pct-display').textContent  = act;
  if (el('bp-acc'))  el('bp-acc').textContent  = fmt(acc);
  if (el('bp-food')) el('bp-food').textContent = fmt(food);
  if (el('bp-act'))  el('bp-act').textContent  = fmt(act);
}

// ---------------------------------------------------------------------------
// Build payload
// ---------------------------------------------------------------------------

function buildPayload() {
  const sd = document.getElementById('start-date').value;
  const ed = document.getElementById('end-date').value;
  const msPerDay = 86400000;
  const total_days = sd && ed
    ? Math.max(1, Math.round((new Date(ed) - new Date(sd)) / msPerDay))
    : 7;

  return {
    start_location:   document.getElementById('start-location').value.trim(),
    main_destination: document.getElementById('main-destination').value.trim(),
    start_date:       sd,
    end_date:         ed,
    total_days,
    adults:           S.adults,
    children:         S.children,
    travel_styles:    S.travelStyles,
    travel_description: (document.getElementById('travel-description') || {}).value || '',
    mandatory_activities: S.mandatoryTags.map(name => ({ name })),
    preferred_activities: [],
    max_activities_per_stop: parseInt(document.getElementById('max-activities')?.value) || 5,
    max_restaurants_per_stop: parseInt(document.getElementById('max-restaurants')?.value) || 3,
    activities_radius_km: parseInt(document.getElementById('activities-radius')?.value) || 30,
    max_drive_hours_per_day: parseFloat(document.getElementById('max-drive-hours')?.value) || 4.5,
    min_nights_per_stop: parseInt(document.getElementById('min-nights')?.value) || 1,
    max_nights_per_stop: parseInt(document.getElementById('max-nights')?.value) || 5,
    accommodation_styles:    getSelectedAccStyles(),
    accommodation_must_haves: getSelectedMustHaves(),
    hotel_radius_km: parseInt(document.getElementById('hotel-radius')?.value) || 10,
    budget_chf: parseFloat(document.getElementById('budget-chf')?.value) || 3000,
    budget_accommodation_pct: parseInt(document.getElementById('budget-acc-pct')?.value)  || 60,
    budget_food_pct:          parseInt(document.getElementById('budget-food-pct')?.value) || 20,
    budget_activities_pct:    parseInt(document.getElementById('budget-act-pct')?.value)  || 20,
    via_points: viaPoints
      .filter(vp => vp.location.trim())
      .map(vp => ({
        location: vp.location.trim(),
        fixed_date: vp.hasDate && vp.date ? vp.date : null,
        notes: vp.notes || null,
      })),
  };
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

function renderSummary() {
  const el = document.getElementById('summary-content');
  if (!el) return;
  const p = buildPayload();
  el.innerHTML = `
    <div class="summary-grid">
      <div class="summary-item"><span class="summary-label">Start</span><span>${esc(p.start_location)}</span></div>
      <div class="summary-item"><span class="summary-label">Ziel</span><span>${esc(p.main_destination)}</span></div>
      <div class="summary-item"><span class="summary-label">Datum</span><span>${esc(p.start_date)} – ${esc(p.end_date)} (${p.total_days} Tage)</span></div>
      <div class="summary-item"><span class="summary-label">Reisende</span><span>${p.adults} Erwachsene${p.children.length ? ', ' + p.children.length + ' Kinder' : ''}</span></div>
      <div class="summary-item"><span class="summary-label">Stile</span><span>${p.travel_styles.map(s => TRAVEL_STYLES.find(t => t.id === s)?.label || s).join(', ') || '–'}</span></div>
      <div class="summary-item"><span class="summary-label">Budget</span><span>CHF ${(p.budget_chf || 0).toLocaleString('de-CH')} (Unterkunft ${p.budget_accommodation_pct}% / Essen ${p.budget_food_pct}% / Aktivitäten ${p.budget_activities_pct}%)</span></div>
      <div class="summary-item"><span class="summary-label">Max. Fahrzeit</span><span>${p.max_drive_hours_per_day}h/Tag</span></div>
      ${p.mandatory_activities.length ? `<div class="summary-item"><span class="summary-label">Pflichtaktivitäten</span><span>${p.mandatory_activities.map(a => esc(a.name)).join(', ')}</span></div>` : ''}
      ${p.via_points.length ? `<div class="summary-item"><span class="summary-label">Via-Punkte</span><span>${p.via_points.map(vp => esc(vp.location)).join(' → ')}</span></div>` : ''}
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

async function submitTrip() {
  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.textContent = 'Plane Reise…';

  try {
    const payload = buildPayload();
    const data = await apiPlanTrip(payload);

    S.jobId = data.job_id;
    S.currentOptions = data.options || [];

    lsSet(LS_ROUTE, { jobId: data.job_id, stops: {}, stopsOrder: [] });
    lsClear(LS_ACCOMMODATIONS);

    showSection('route-builder');
    startRouteBuilding(data);

  } catch (err) {
    alert('Fehler beim Starten der Reiseplanung: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Reise planen';
  }
}

// ---------------------------------------------------------------------------
// Auto-save / restore
// ---------------------------------------------------------------------------

function saveFormToCache() {
  const p = buildPayload();
  lsSet(LS_FORM, { ...p, viaPoints, travelStyles: S.travelStyles, children: S.children, mandatoryTags: S.mandatoryTags });
  updateQuickSubmitBar();
}

function setupFormAutoSave() {
  document.querySelectorAll('#form-section input, #form-section select, #form-section textarea')
    .forEach(el => { el.addEventListener('change', saveFormToCache); });
}

function restoreFormFromCache() {
  const cached = lsGet(LS_FORM);
  if (!cached) return;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val != null) el.value = val;
  };

  setVal('start-location', cached.start_location);
  setVal('main-destination', cached.main_destination);
  setVal('start-date', cached.start_date);
  setVal('end-date', cached.end_date);
  setVal('budget-chf', cached.budget_chf);
  setVal('max-drive-hours', cached.max_drive_hours_per_day);
  setVal('hotel-radius', cached.hotel_radius_km);
  setVal('activities-radius', cached.activities_radius_km);
  setVal('min-nights', cached.min_nights_per_stop);
  setVal('max-nights', cached.max_nights_per_stop);
  setVal('budget-acc-pct',  cached.budget_accommodation_pct);
  setVal('budget-food-pct', cached.budget_food_pct);
  setVal('budget-act-pct',  cached.budget_activities_pct);
  setVal('max-activities',  cached.max_activities_per_stop);
  setVal('max-restaurants', cached.max_restaurants_per_stop);

  if (cached.travelStyles) {
    S.travelStyles = cached.travelStyles;
    S.travelStyles.forEach(id => {
      const card = document.querySelector(`.style-card[data-id="${id}"]`);
      if (card) card.classList.add('selected');
    });
  }

  if (cached.mandatoryTags) {
    S.mandatoryTags = cached.mandatoryTags;
    renderTags();
  }

  if (cached.children) {
    S.children = cached.children;
    renderChildren();
  }

  if (cached.adults) {
    S.adults = cached.adults;
    document.getElementById('adults-count').textContent = S.adults;
  }

  if (cached.viaPoints) {
    viaPoints = cached.viaPoints;
    renderViaPoints();
  }

  updateBudgetPreview();
}

function clearAppData() {
  if (!confirm('Alle gespeicherten Daten löschen und neu starten? Die Formularfelder bleiben erhalten.')) return;

  // Close any open SSE connections
  if (S.sse) { try { S.sse.close(); } catch (e) {} S.sse = null; }
  if (typeof accSSE !== 'undefined' && accSSE) { try { accSSE.close(); } catch (e) {} }

  // Clear all non-form localStorage keys
  lsClear(LS_ROUTE);
  lsClear(LS_ACCOMMODATIONS);
  lsClear(LS_RESULT);

  // Reset runtime state (keep form-related fields)
  S.step = 1;
  S.jobId = null;
  S.logs = [];
  S.apiCalls = 0;
  S.debugOpen = false;
  S.result = null;
  S.selectedStops = [];
  S.currentOptions = [];
  S.loadingOptions = false;
  S.confirmingRoute = false;
  S.allStops = [];
  S.selectedAccommodations = {};
  S.prefetchedOptions = {};
  S.pendingSelections = {};
  S.allAccLoaded = false;
  S.accSelectionCount = 0;

  // Hide resume banner
  document.getElementById('resume-banner').style.display = 'none';

  // Return to form step 1
  goToStep(1);
  showSection('form-section');
}

function checkResume() {
  const result = lsGet(LS_RESULT);
  if (result && result.jobId) {
    document.getElementById('resume-banner').style.display = 'flex';
  }
}

function resumeResult() {
  const saved = lsGet(LS_RESULT);
  if (!saved) return;
  S.jobId = saved.jobId;
  S.result = saved.plan;
  showTravelGuide(saved.plan);
  showSection('travel-guide');
}

function dismissResume() {
  document.getElementById('resume-banner').style.display = 'none';
}
