'use strict';

// Form — 5-step trip planning wizard; collects legs, preferences, and budget.
// Reads: S (state.js), Router (router.js), GoogleMaps (maps-core.js), t (i18n.js), esc (core).
// Provides: initForm, goToStep, buildPayload, submitTrip, clearAppData, updateQuickSubmitBar, renderOrtsreiseForm, submitLocationTrip, showModePicker.

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

/** Bootstraps the form: styles, sliders, autosave, and leg rendering. */
function initForm() {
  initTravelStyles();
  initSliders();
  initBudgetSliders();
  setupFormAutoSave();
  restoreFormFromCache();
  initLegs();
  updateQuickSubmitBar();

  // Re-render legs when Google Maps API loads (for autocomplete attachment)
  document.addEventListener('google-maps-ready', () => renderLegs());

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

/** Navigates to the given step number, updating indicators and the URL. */
function goToStep(n) {
  S.step = n;
  document.querySelectorAll('.form-step').forEach((el, i) => {
    el.classList.toggle('active', i + 1 === n);
  });
  const steps = document.querySelectorAll('.step-indicator .step');
  steps.forEach((el, i) => {
    const isDone = i + 1 < n;
    el.classList.toggle('active', i + 1 === n);
    el.classList.toggle('done', isDone);
    if (isDone) {
      el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="14" height="14" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;
    } else {
      el.textContent = String(i + 1);
    }
  });
  document.querySelectorAll('.step-connector').forEach((el, i) => {
    el.classList.toggle('done', i + 1 < n);
  });
  Router.navigate('/form/step/' + n, { replace: true });
  window.scrollTo(0, 0);
  // Re-bind click handlers on done steps
  document.querySelectorAll('.step-indicator .step').forEach((el, i) => {
    const stepNum = i + 1;
    if (el.classList.contains('done')) {
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-label', t('form.back_to_step_aria', {step: stepNum}));
      el.onclick = () => goToStep(stepNum);
      el.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToStep(stepNum); } };
    } else {
      el.removeAttribute('role');
      el.removeAttribute('tabindex');
      el.onclick = null;
      el.onkeydown = null;
    }
  });
  updateQuickSubmitBar();
  if (typeof updateSidebar === 'function') updateSidebar();
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

function _setFieldError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('invalid');
  let errEl = el.parentElement.querySelector('.field-error');
  if (!errEl) {
    errEl = document.createElement('span');
    errEl.className = 'field-error';
    el.after(errEl);
  }
  errEl.textContent = msg;
  el.focus();
}

function _clearFieldErrors(ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('invalid');
    const errEl = el.parentElement.querySelector('.field-error');
    if (errEl) errEl.textContent = '';
  });
}

function validateStep(n) {
  if (n === 1) {
    // Collect all leg field IDs for clearing
    const fieldIds = [];
    S.legs.forEach((_, i) => {
      fieldIds.push(`leg-start-${i}`, `leg-end-${i}`, `leg-sdate-${i}`, `leg-edate-${i}`, `explore-text-${i}`);
    });
    _clearFieldErrors(fieldIds);

    let valid = true;
    for (let i = 0; i < S.legs.length; i++) {
      const leg = S.legs[i];
      if (leg.mode === "explore") {
        // Explore legs need a start location (departure point) and description
        if (!leg.start_location || !leg.start_location.trim()) {
          _setFieldError(`leg-start-${i}`, t('form.start_location_required'));
          if (valid) valid = false;
        }
        if (!leg.explore_description || !leg.explore_description.trim()) {
          _setFieldError(`explore-text-${i}`, t('form.explore_description_required'));
          if (valid) valid = false;
        }
      } else {
        // Transit legs need locations
        if (!leg.start_location) {
          _setFieldError(`leg-start-${i}`, t('form.start_location_required'));
          if (valid) valid = false;
        }
        if (!leg.end_location) {
          _setFieldError(`leg-end-${i}`, t('form.end_location_required'));
          if (valid) valid = false;
        }
      }
      if (!leg.start_date) {
        _setFieldError(`leg-sdate-${i}`, t('form.start_date_required'));
        if (valid) valid = false;
      }
      if (!leg.end_date) {
        _setFieldError(`leg-edate-${i}`, t('form.end_date_required'));
        if (valid) valid = false;
      }
      if (leg.start_date && leg.end_date && leg.start_date >= leg.end_date) {
        _setFieldError(`leg-edate-${i}`, t('form.end_date_after_start'));
        if (valid) valid = false;
      }
    }
    return valid;
  }
  if (n === 5) {
    const acc  = parseInt(document.getElementById('budget-acc-pct')?.value)  || 0;
    const food = parseInt(document.getElementById('budget-food-pct')?.value) || 0;
    const act  = parseInt(document.getElementById('budget-act-pct')?.value)  || 0;
    if (acc + food + act !== 100) {
      alert(t('form.budget_must_equal_100'));
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

/** Shows or hides the sticky quick-submit bar based on form readiness. */
function updateQuickSubmitBar() {
  const bar = document.getElementById('quick-submit-bar');
  if (!bar) return;
  const formActive = document.getElementById('form-section')?.classList.contains('active');
  const onSummaryStep = S.step === 6;
  // Check if all legs have valid data
  const legsReady = S.legs.length > 0 && S.legs.every(l => {
    const datesOk = l.start_date && l.end_date && l.start_date < l.end_date;
    if (l.mode === "explore") return datesOk && l.start_location && l.explore_description && l.explore_description.trim();
    return datesOk && l.start_location && l.end_location;
  });
  const ready = formActive && legsReady && !onSummaryStep;
  bar.classList.toggle('visible', !!ready);
}

async function quickSubmitTrip() {
  // Validate legs
  const legsReady = S.legs.length > 0 && S.legs.every(l => {
    const datesOk = l.start_date && l.end_date && l.start_date < l.end_date;
    if (l.mode === "explore") return datesOk && l.start_location && l.explore_description && l.explore_description.trim();
    return datesOk && l.start_location && l.end_location;
  });
  if (!legsReady) { alert(t('form.complete_all_segments')); return; }
  await submitTrip();
}

function toggleSettings() {
  const menu = document.getElementById('settings-menu');
  const btn  = document.querySelector('.settings-btn');
  if (!menu) return;
  const open = menu.style.display !== 'none';
  menu.style.display = open ? 'none' : 'block';
  menu.setAttribute('aria-hidden', open ? 'true' : 'false');
  if (btn) btn.setAttribute('aria-expanded', String(!open));
}

function toggleAdvanced() {
  const btn = document.getElementById('advanced-toggle-btn');
  const section = document.getElementById('advanced-section');
  if (!btn || !section) return;
  const open = section.classList.toggle('open');
  btn.setAttribute('aria-expanded', String(open));
}

// ---------------------------------------------------------------------------
// Legs builder
// ---------------------------------------------------------------------------

function dateDiffDays(start, end) {
  const s = new Date(start), e = new Date(end);
  return Math.round((e - s) / (1000 * 60 * 60 * 24));
}

function addDays(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("de-CH", { day: "numeric", month: "short" });
}

function initLegs() {
  if (S.legs.length === 0) {
    S.legs = [{
      leg_id: "leg-0",
      start_location: '',
      end_location: '',
      start_date: '',
      end_date: '',
      mode: "transit",
      via_points: [],
      zone_bbox: null,
      zone_guidance: [],
      explore_description: '',
    }];
  }
  renderLegs();
}

function _attachLegAutocomplete(legIndex, field) {
  const inputId = field === 'start' ? `leg-start-${legIndex}` : `leg-end-${legIndex}`;
  const acOpts = { types: ['(cities)'], fields: ['formatted_address', 'place_id', 'geometry'] };
  const ac = GoogleMaps.attachAutocomplete(inputId, acOpts);
  if (!ac) return;
  ac.addListener('place_changed', () => {
    const place = ac.getPlace();
    if (place && place.formatted_address) {
      const val = place.formatted_address;
      const placeId = (place.place && place.place.id) || null;
      if (field === 'start') {
        updateLegField(legIndex, 'start_location', val);
        if (placeId) updateLegField(legIndex, 'start_place_id', placeId);
      } else {
        updateLegField(legIndex, 'end_location', val);
        if (placeId) updateLegField(legIndex, 'end_place_id', placeId);
      }
    }
    saveFormToCache();
    updateQuickSubmitBar();
  });
}

function updateLegField(index, field, value) {
  S.legs[index][field] = value;
  // Chain: end_location → next leg's start_location (skip explore legs)
  if (field === 'end_location' && index < S.legs.length - 1
      && S.legs[index + 1].mode === 'transit') {
    S.legs[index + 1].start_location = value;
    const nextInput = document.getElementById(`leg-start-${index + 1}`);
    if (nextInput) nextInput.value = value;
  }
  saveFormToCache();
  updateQuickSubmitBar();
  if (typeof updateSidebar === 'function') updateSidebar();
}

function updateLegDate(index, field, value) {
  S.legs[index][field] = value;
  // Chain: end_date → next leg's start_date
  if (field === 'end_date' && index < S.legs.length - 1) {
    S.legs[index + 1].start_date = value;
    const nextInput = document.getElementById(`leg-sdate-${index + 1}`);
    if (nextInput) nextInput.value = value;
  }
  // Update days label
  const leg = S.legs[index];
  const daysLabel = document.getElementById(`leg-days-${index}`);
  if (daysLabel && leg.start_date && leg.end_date) {
    const days = dateDiffDays(leg.start_date, leg.end_date);
    daysLabel.textContent = days !== 1 ? t('form.days_label_plural', {days}) : t('form.days_label', {days});
  }
  saveFormToCache();
  updateQuickSubmitBar();
}

function renderLegs() {
  const container = document.getElementById("legs-container");
  if (!container) return;
  container.innerHTML = S.legs.map((leg, i) => renderLegCard(leg, i)).join("");

  // Attach autocomplete if Google Maps is ready (transit legs only)
  const gmReady = typeof google !== 'undefined' && google.maps && google.maps.places;
  S.legs.forEach((leg, i) => {
    if (gmReady) {
      // Start field: first leg only (others are chained/readonly), all modes
      if (i === 0) _attachLegAutocomplete(i, 'start');
      // End field: transit only
      if (leg.mode === "transit") _attachLegAutocomplete(i, 'end');
    }
  });
}

function renderLegCard(leg, index) {
  const isFirst = index === 0;
  const modeColor = leg.mode === "explore" ? "#e0b840" : "#4a90d9";
  const days = leg.start_date && leg.end_date ? dateDiffDays(leg.start_date, leg.end_date) : 0;
  const canDelete = S.legs.length > 1;

  // Location row — start location shown for all modes, end location only for transit
  const startReadonly = !isFirst ? 'readonly tabindex="-1"' : '';
  const startClass = !isFirst ? 'leg-input-chained' : '';
  const locationRow = `
    <div class="leg-location-row">
      <div class="form-group">
        <label for="leg-start-${index}">${t('form.leg_from_label')}</label>
        <input type="text" id="leg-start-${index}" class="${startClass}"
          value="${esc(leg.start_location)}" placeholder="${t('form.leg_from_placeholder')}"
          ${startReadonly}
          oninput="updateLegField(${index}, 'start_location', this.value)">
      </div>
      ${leg.mode === "transit" ? `
      <div class="form-group">
        <label for="leg-end-${index}">${t('form.leg_to_label')}</label>
        <input type="text" id="leg-end-${index}"
          value="${esc(leg.end_location)}" placeholder="${t('form.leg_to_placeholder')}"
          oninput="updateLegField(${index}, 'end_location', this.value)">
      </div>` : ''}
    </div>`;

  // Date row
  const sdateReadonly = !isFirst ? 'readonly tabindex="-1"' : '';
  const sdateClass = !isFirst ? 'leg-input-chained' : '';
  const dateRow = `
    <div class="leg-date-row">
      <div class="form-group">
        <label for="leg-sdate-${index}">${t('form.leg_start_date_label')}</label>
        <input type="date" id="leg-sdate-${index}" class="${sdateClass}"
          value="${leg.start_date}" ${sdateReadonly}
          oninput="updateLegDate(${index}, 'start_date', this.value)">
      </div>
      <div class="form-group">
        <label for="leg-edate-${index}">${t('form.leg_end_date_label')}</label>
        <input type="date" id="leg-edate-${index}"
          value="${leg.end_date}"
          oninput="updateLegDate(${index}, 'end_date', this.value)">
      </div>
    </div>`;

  const transitContent = leg.mode === "transit" ? `
      <div class="leg-via-points">
          <label class="form-label-sm">${t('form.via_points_label')}</label>
          <div class="tag-input" id="via-tags-${index}">
              ${(leg.via_points || []).map(vp => `
                  <span class="tag">${esc(vp.location)}
                      <button onclick="removeViaPoint(${index}, '${esc(vp.location)}')" aria-label="${t('form.via_point_remove_aria')}">×</button>
                  </span>`).join("")}
              <input type="text" placeholder="${t('form.via_point_placeholder')}"
                  onkeydown="handleViaInput(event, ${index})"
                  class="tag-input-field">
          </div>
      </div>` : "";

  const exploreContent = leg.mode === "explore" ? `
      <div class="leg-zone">
          <label class="form-label-sm">${t('form.explore_label')}</label>
          <textarea id="explore-text-${index}" class="input-sm"
              placeholder="${t('form.explore_placeholder')}"
              rows="3"
              oninput="S.legs[${index}].explore_description = this.value"
          >${esc(leg.explore_description || '')}</textarea>
      </div>` : "";

  return `
  <div class="leg-card" id="leg-card-${index}" style="border-color:${modeColor}">
      <div class="leg-card-header" style="background:${leg.mode === 'explore' ? '#fdf8e8' : '#f5f5f5'}">
          <div class="leg-badge" style="background:${modeColor}">${index + 1}</div>
          <span class="leg-days-label" id="leg-days-${index}">${days > 0 ? (days !== 1 ? t('form.days_label_plural', {days}) : t('form.days_label', {days})) : ''}</span>
          <div class="leg-controls">
              <div class="mode-toggle">
                  <button class="mode-btn ${leg.mode === 'transit' ? 'active' : ''}"
                      onclick="setLegMode(${index}, 'transit')" style="border-color:${modeColor}">${t('form.transit_mode')}</button>
                  <button class="mode-btn ${leg.mode === 'explore' ? 'active' : ''}"
                      onclick="setLegMode(${index}, 'explore')" style="border-color:${modeColor}">${t('form.explore_mode')}</button>
              </div>
              ${canDelete ? `<button class="leg-delete-btn" onclick="removeLeg(${index})" aria-label="${t('form.remove_segment_aria')}">×</button>` : ""}
          </div>
      </div>
      <div class="leg-card-body">
          ${locationRow}
          ${dateRow}
          ${transitContent}
          ${exploreContent}
      </div>
  </div>`;
}

function addLeg() {
  const prevLeg = S.legs[S.legs.length - 1];
  const originalEnd = prevLeg.end_location || '';
  const originalEndDate = prevLeg.end_date || '';

  // Split dates: give half the previous leg's days to the new segment
  let splitDate = originalEndDate;
  if (prevLeg.start_date && prevLeg.end_date) {
    const totalDays = dateDiffDays(prevLeg.start_date, prevLeg.end_date);
    if (totalDays < 2) {
      alert(t('form.segment_too_short_to_split'));
      return;
    }
    const halfDays = Math.max(1, Math.floor(totalDays / 2));
    splitDate = addDays(prevLeg.start_date, halfDays);
    prevLeg.end_date = splitDate;
  }

  S.legs.push({
    leg_id: `leg-${S.legs.length}`,
    start_location: originalEnd,
    end_location: originalEnd,
    start_date: splitDate,
    end_date: originalEndDate,
    mode: "transit",
    via_points: [],
    zone_bbox: null,
    zone_guidance: [],
    explore_description: '',
  });
  S.legs.forEach((leg, i) => { leg.leg_id = `leg-${i}`; });
  renderLegs();
  saveFormToCache();
}

function removeLeg(index) {
  if (S.legs.length <= 1) return;

  if (index === 0) {
    // First leg removed: next leg inherits start_location + start_date
    S.legs[1].start_location = S.legs[0].start_location;
    S.legs[1].start_date = S.legs[0].start_date;
  } else if (index === S.legs.length - 1) {
    // Last leg removed: prev leg inherits end_location + end_date
    S.legs[index - 1].end_location = S.legs[index].end_location;
    S.legs[index - 1].end_date = S.legs[index].end_date;
  } else {
    // Middle leg removed: prev leg's end connects to next leg's start
    S.legs[index - 1].end_location = S.legs[index + 1].start_location;
    S.legs[index - 1].end_date = S.legs[index + 1].start_date;
  }

  S.legs.splice(index, 1);
  S.legs.forEach((leg, i) => { leg.leg_id = `leg-${i}`; });
  renderLegs();
  saveFormToCache();
}

function setLegMode(index, mode) {
  S.legs[index].mode = mode;
  if (mode === "explore") {
    // Clear transit-specific fields (keep start_location — needed as departure point)
    S.legs[index].end_location = '';
    S.legs[index].via_points = [];
    if (!S.legs[index].explore_description) {
      S.legs[index].explore_description = '';
    }
  } else {
    // Clear explore-specific fields
    S.legs[index].explore_description = '';
    S.legs[index].zone_bbox = null;
    S.legs[index].zone_guidance = [];
  }
  renderLegs();
  saveFormToCache();
}

function handleViaInput(event, legIndex) {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    const val = event.target.value.trim().replace(/,$/, "");
    if (val) {
      S.legs[legIndex].via_points.push({ location: val, fixed_date: null, notes: null });
      event.target.value = "";
      renderLegs();
    }
  }
}

function removeViaPoint(legIndex, location) {
  S.legs[legIndex].via_points = S.legs[legIndex].via_points.filter(vp => vp.location !== location);
  renderLegs();
}

// ---------------------------------------------------------------------------
// Travel styles
// ---------------------------------------------------------------------------

function initTravelStyles() {
  const grid = document.getElementById('travel-style-grid');
  if (!grid) return;
  grid.innerHTML = TRAVEL_STYLES.map(style => `
    <div class="style-card" data-id="${esc(style.id)}" onclick="toggleStyle(this)"
         tabindex="0" role="button" aria-pressed="false">
      <div class="style-icon">${style.icon}</div>
      <div class="style-label">${esc(t('travel_styles.' + style.id))}</div>
    </div>
  `).join('');
}

function toggleStyle(card) {
  const id = card.dataset.id;
  card.classList.toggle('selected');
  const isSelected = card.classList.contains('selected');
  card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
  if (isSelected) {
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

function renderTags() {
  const container = document.getElementById('mandatory-tags');
  if (!container) return;
  container.innerHTML = '';
  S.mandatoryTags.forEach((tag, i) => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = tag;
    const btn = document.createElement('button');
    btn.textContent = '×';
    btn.title = t('form.via_point_remove_aria');
    btn.setAttribute('aria-label', t('form.tag_remove_aria', {tag}));
    btn.addEventListener('click', () => removeTag(i));
    span.appendChild(btn);
    container.appendChild(span);
  });
}

function removeTag(idx) {
  S.mandatoryTags.splice(idx, 1);
  renderTags();
  saveFormToCache();
}

function addPreferredTagFromInput() {
  const input = document.getElementById('preferred-tag-input');
  if (!input) return;
  const val = input.value.trim();
  if (val && !S.preferredTags.includes(val)) {
    S.preferredTags.push(val);
    renderPreferredTags();
    input.value = '';
    saveFormToCache();
  }
}

function renderPreferredTags() {
  const container = document.getElementById('preferred-tags');
  if (!container) return;
  while (container.firstChild) container.removeChild(container.firstChild);
  S.preferredTags.forEach((tag, i) => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = tag;
    const btn = document.createElement('button');
    btn.textContent = '×';
    btn.title = t('form.via_point_remove_aria');
    btn.setAttribute('aria-label', t('form.tag_remove_aria', {tag}));
    btn.addEventListener('click', () => removePreferredTag(i));
    span.appendChild(btn);
    container.appendChild(span);
  });
}

function removePreferredTag(idx) {
  S.preferredTags.splice(idx, 1);
  renderPreferredTags();
  saveFormToCache();
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
      <label>${t('form.child_row_label', {index: i + 1})}</label>
      <input type="number" min="0" max="17" value="${child.age}"
        oninput="S.children[${i}].age = parseInt(this.value) || 0; saveFormToCache()">
      <button class="btn-icon btn-danger" onclick="removeChild(${i})" aria-label="${t('form.remove_child_aria', {index: i + 1})}">×</button>
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
// Accommodation preferences
// ---------------------------------------------------------------------------

function getAccPreferences() {
  return ['acc-pref-0', 'acc-pref-1', 'acc-pref-2']
    .map(id => document.getElementById(id)?.value.trim() || '')
    .filter(v => v.length > 0);
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
  const sliders = ['budget-acc-pct', 'budget-food-pct', 'budget-act-pct'];
  sliders.forEach(changedId => {
    const el = document.getElementById(changedId);
    if (!el) return;
    el.oninput = () => {
      _autoBalanceBudget(changedId);
      updateBudgetPreview();
      saveFormToCache();
    };
  });
  const budgetInput = document.getElementById('budget-chf');
  if (budgetInput) budgetInput.oninput = () => { updateBudgetPreview(); saveFormToCache(); };
  updateBudgetPreview();
}

function _autoBalanceBudget(changedId) {
  const ids = ['budget-acc-pct', 'budget-food-pct', 'budget-act-pct'];
  const others = ids.filter(id => id !== changedId);
  const changedEl = document.getElementById(changedId);
  if (!changedEl) return;
  const changedVal = parseInt(changedEl.value) || 0;
  const remaining = 100 - changedVal;
  const [a, b] = others.map(id => document.getElementById(id));
  if (!a || !b) return;
  const aVal = parseInt(a.value) || 0;
  const bVal = parseInt(b.value) || 0;
  const total = aVal + bVal;
  if (total === 0) {
    const half = Math.floor(remaining / 2);
    a.value = half;
    b.value = remaining - half;
  } else {
    const aNew = Math.max(5, Math.round(remaining * aVal / total));
    const bNew = Math.max(5, remaining - aNew);
    a.value = aNew;
    b.value = bNew;
  }
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
    const valid = sum === 100;
    checkEl.classList.toggle('invalid', !valid);
    const icon = document.getElementById('budget-check-icon');
    if (icon) {
      icon.style.display = valid ? '' : 'none';
    }
    // Show/hide error hint after the sum
    let errSpan = checkEl.querySelector('.budget-sum-error');
    if (!errSpan) {
      errSpan = document.createElement('span');
      errSpan.className = 'budget-sum-error';
      errSpan.style.cssText = 'margin-left:6px;font-size:13px;color:var(--danger)';
      checkEl.appendChild(errSpan);
    }
    errSpan.textContent = valid ? '' : t('form.budget_sum_error');
  }

  const fmt = v => Math.round(total * v / 100).toLocaleString('de-CH');
  const el  = id => document.getElementById(id);
  if (el('budget-acc-pct-display'))  el('budget-acc-pct-display').textContent  = acc;
  if (el('budget-food-pct-display')) el('budget-food-pct-display').textContent = food;
  if (el('budget-act-pct-display'))  el('budget-act-pct-display').textContent  = act;
  if (el('bp-acc'))  el('bp-acc').textContent  = fmt(acc);
  if (el('bp-food')) el('bp-food').textContent = fmt(food);
  if (el('bp-act'))  el('bp-act').textContent  = fmt(act);

  // Update visual budget bar
  if (el('bvb-acc'))  el('bvb-acc').style.width  = acc  + '%';
  if (el('bvb-food')) el('bvb-food').style.width = food + '%';
  if (el('bvb-act'))  el('bvb-act').style.width  = act  + '%';
}

// ---------------------------------------------------------------------------
// Build payload
// ---------------------------------------------------------------------------

/** Assembles the full TravelRequest payload from current form state and DOM values. */
function buildPayload() {
  const firstLeg = S.legs[0] || {};
  const lastLeg = S.legs[S.legs.length - 1] || {};
  const sd = firstLeg.start_date || '';
  const ed = lastLeg.end_date || '';
  const msPerDay = 86400000;
  const total_days = sd && ed
    ? Math.max(1, Math.round((new Date(ed) - new Date(sd)) / msPerDay))
    : 7;

  // Clean legs for payload: strip internal fields, filter mode-irrelevant data
  const cleanLegs = S.legs.map(leg => {
    const { _pending_zone_label, ...clean } = leg;
    if (clean.mode === "explore") {
      // Keep start_location — explore legs need a departure point
      clean.end_location = '';
      clean.via_points = [];
    } else {
      delete clean.explore_description;
      delete clean.zone_bbox;
      delete clean.zone_guidance;
    }
    return clean;
  });

  return {
    legs:             cleanLegs,
    total_days,
    adults:           S.adults,
    children:         S.children,
    travel_styles:    S.travelStyles,
    travel_description: (document.getElementById('travel-description') || {}).value || '',
    mandatory_activities: S.mandatoryTags.map(name => ({ name })),
    preferred_activities: S.preferredTags,
    max_activities_per_stop: parseInt(document.getElementById('max-activities')?.value) || 5,
    max_restaurants_per_stop: parseInt(document.getElementById('max-restaurants')?.value) || 3,
    activities_radius_km: parseInt(document.getElementById('activities-radius')?.value) || 30,
    max_drive_hours_per_day: parseFloat(document.getElementById('max-drive-hours')?.value) || 4.5,
    proximity_origin_pct: parseInt(document.getElementById('proximity-origin')?.value) ?? 10,
    proximity_target_pct: parseInt(document.getElementById('proximity-target')?.value) ?? 15,
    min_nights_per_stop: parseInt(document.getElementById('min-nights')?.value) || 1,
    max_nights_per_stop: parseInt(document.getElementById('max-nights')?.value) || 5,
    accommodation_preferences: getAccPreferences(),
    hotel_radius_km: parseInt(document.getElementById('hotel-radius')?.value) || 10,
    budget_chf: parseFloat(document.getElementById('budget-chf')?.value) || 3000,
    budget_accommodation_pct: parseInt(document.getElementById('budget-acc-pct')?.value)  || 60,
    budget_food_pct:          parseInt(document.getElementById('budget-food-pct')?.value) || 20,
    budget_activities_pct:    parseInt(document.getElementById('budget-act-pct')?.value)  || 20,
    log_verbosity:            document.getElementById('log-verbosity')?.value || 'normal',
    language:                 (typeof getLocale === 'function') ? getLocale() : 'de',
  };
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

function renderSummary() {
  const el = document.getElementById('summary-content');
  if (!el) return;
  const p = buildPayload();
  const firstLeg = S.legs[0] || {};
  const lastLeg = S.legs[S.legs.length - 1] || {};
  const legsDisplay = S.legs.map(l => {
    if (l.mode === 'explore') return t('form.explore_prefix') + ' ' + esc(l.explore_description || '').substring(0, 50);
    return esc(l.start_location) + ' → ' + esc(l.end_location);
  }).join(' | ');
  const startDisplay = firstLeg.mode === 'explore'
    ? t('form.explore_prefix') + ' ' + esc(firstLeg.explore_description || '').substring(0, 50)
    : esc(firstLeg.start_location);
  const endDisplay = lastLeg.mode === 'explore'
    ? t('form.explore_prefix') + ' ' + esc(lastLeg.explore_description || '').substring(0, 50)
    : esc(lastLeg.end_location);
  el.innerHTML = `
    <div class="summary-grid">
      <div class="summary-item"><span class="summary-label">Start</span><span>${startDisplay}</span></div>
      <div class="summary-item"><span class="summary-label">Ziel</span><span>${endDisplay}</span></div>
      <div class="summary-item"><span class="summary-label">Datum</span><span>${formatDate(firstLeg.start_date)} – ${formatDate(lastLeg.end_date)} (${p.total_days} Tage)</span></div>
      <div class="summary-item"><span class="summary-label">${t('form.travelers_summary', {adults: p.adults})}${p.children.length ? t('form.children_count_summary', {count: p.children.length}) : ''}</span></div>
      <div class="summary-item"><span class="summary-label">${t('form.styles_summary_label')}</span><span>${p.travel_styles.map(s => t('travel_styles.' + s)).join(', ') || '–'}</span></div>
      <div class="summary-item"><span class="summary-label">Budget</span><span>CHF ${(p.budget_chf || 0).toLocaleString('de-CH')} (${t('form.budget_accommodation_label')} ${p.budget_accommodation_pct}% / ${t('form.budget_food_label')} ${p.budget_food_pct}% / ${t('form.budget_activities_label')} ${p.budget_activities_pct}%)</span></div>
      <div class="summary-item"><span class="summary-label">${t('form.max_drive_summary_label')}</span><span>${p.max_drive_hours_per_day}h/Tag</span></div>
      ${p.mandatory_activities.length ? `<div class="summary-item"><span class="summary-label">${t('form.mandatory_summary_label')}</span><span>${p.mandatory_activities.map(a => esc(a.name)).join(', ')}</span></div>` : ''}
      ${p.preferred_activities.length ? `<div class="summary-item"><span class="summary-label">${t('form.preferred_summary_label')}</span><span>${p.preferred_activities.map(a => esc(a)).join(', ')}</span></div>` : ''}
      <div class="summary-item"><span class="summary-label">${t('form.segments_summary_label')}</span><span>${legsDisplay}</span></div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

function _showFormError(msg) {
  const el = document.getElementById('submit-error');
  if (!el) return;
  el.textContent = msg;
  el.style.display = '';
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/** Validates, submits the trip payload, and transitions to route-builder with SSE streaming. */
async function submitTrip() {
  const btn = document.getElementById('submit-btn');
  const errEl = document.getElementById('submit-error');
  if (errEl) errEl.style.display = 'none';
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> ' + esc(t('form.planning_trip'));

  try {
    const payload = buildPayload();

    // 1. Pre-init job so we can open SSE before Claude starts
    const initData = await apiInitJob(payload);
    const preJobId = initData.job_id;
    S.jobId = preJobId;

    lsSet(LS_ROUTE, { jobId: preJobId, stops: {}, stopsOrder: [] });
    lsClear(LS_ACCOMMODATIONS);

    // 2. Show route-builder section with skeleton cards, then open SSE
    showSection('route-builder');
    Router.navigate('/route-builder/' + preJobId);
    _showSkeletonCards();
    progressOverlay.open('Zwischenstopps werden gesucht…');
    openRouteSSE(preJobId);

    // 3. Trigger actual planning (Claude + OSRM); SSE delivers options progressively
    const data = await apiPlanTrip(payload, preJobId);

    S.currentOptions = data.options || [];
    startRouteBuilding(data);

  } catch (err) {
    const msg = err.message || '';
    if (msg.startsWith('HTTP 402:')) {
      _showFormError(msg.replace('HTTP 402: ', ''));
    } else {
      alert(t('form.trip_planning_error') + ' ' + msg);
    }
    btn.disabled = false;
    btn.textContent = t('form.plan_trip');
  }
}

// ---------------------------------------------------------------------------
// Auto-save / restore
// ---------------------------------------------------------------------------

function saveFormToCache() {
  const p = buildPayload();
  lsSet(LS_FORM, { ...p, travelStyles: S.travelStyles, children: S.children, mandatoryTags: S.mandatoryTags, preferredTags: S.preferredTags });
  lsSet(LS_APP_MODE, S.appMode);
  updateQuickSubmitBar();
}

function setupFormAutoSave() {
  document.querySelectorAll('#form-section input, #form-section select, #form-section textarea')
    .forEach(el => { el.addEventListener('change', saveFormToCache); });
  // Settings menu lives outside #form-section — attach separately
  ['max-activities', 'max-restaurants', 'log-verbosity'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', saveFormToCache);
  });
}

function restoreFormFromCache() {
  const cached = lsGet(LS_FORM);
  if (!cached) return;

  // Restore appMode separately (stored under its own key)
  const savedMode = lsGet(LS_APP_MODE);
  if (savedMode) S.appMode = savedMode;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val != null) el.value = val;
  };

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
  setVal('proximity-origin', cached.proximity_origin_pct);
  setVal('proximity-target', cached.proximity_target_pct);
  setVal('travel-description', cached.travel_description);
  setVal('log-verbosity', cached.log_verbosity);

  // Sync slider display labels
  ['hotel-radius', 'activities-radius', 'max-drive-hours', 'proximity-origin', 'proximity-target'].forEach(id => {
    const s = document.getElementById(id);
    const d = document.getElementById(id + '-display');
    if (s && d) d.textContent = s.value;
  });

  if (cached.accommodation_preferences) {
    cached.accommodation_preferences.forEach((val, i) => setVal(`acc-pref-${i}`, val));
  }

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

  if (cached.preferredTags) {
    S.preferredTags = cached.preferredTags;
    renderPreferredTags();
  }

  if (cached.children) {
    S.children = cached.children;
    renderChildren();
  }

  if (cached.adults) {
    S.adults = cached.adults;
    document.getElementById('adults-count').textContent = S.adults;
  }

  // Restore legs — handle legacy cache that used top-level start/end fields
  if (cached.legs && cached.legs.length > 0) {
    S.legs = cached.legs;
  } else if (cached.start_location || cached.main_destination) {
    S.legs = [{
      leg_id: "leg-0",
      start_location: cached.start_location || '',
      end_location: cached.main_destination || '',
      start_date: cached.start_date || '',
      end_date: cached.end_date || '',
      mode: "transit",
      via_points: [],
      zone_bbox: null,
      zone_guidance: [],
    }];
  }

  updateBudgetPreview();
}

/** Resets all app state and localStorage, then returns to form step 1. */
function clearAppData() {
  if (!confirm(t('form.confirm_clear_data'))) return;

  // Close any open SSE connections
  if (S.sse) { try { S.sse.close(); } catch (e) {} S.sse = null; }
  if (typeof accSSE !== 'undefined' && accSSE) { try { accSSE.close(); } catch (e) {} }

  // Clear all non-form localStorage keys
  lsClear(LS_ROUTE);
  lsClear(LS_ACCOMMODATIONS);
  lsClear(LS_RESULT);
  lsClear(LS_APP_MODE);

  // Reset runtime state (keep form-related fields)
  S.step = 1;
  S.legs = [];
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
  S.appMode = null;
  S.locationQuery = '';
  S.locationNights = 7;
  S.ortsreiseDescription = '';

  // Hide resume banner
  document.getElementById('resume-banner').style.display = 'none';

  // Return to form step 1
  goToStep(1);
  Router.navigate('/');
}

// ---------------------------------------------------------------------------
// Ortsreise — single-location form
// ---------------------------------------------------------------------------

/**
 * Renders a single-page scrollable Ortsreise form inside #form-section,
 * replacing the step wizard. Called when S.appMode === 'ortsreise'.
 */
function renderOrtsreiseForm() {
  const section = document.getElementById('form-section');
  if (!section) return;

  // Build travel style grid HTML with current selection state
  const stylesHtml = TRAVEL_STYLES.map(style => {
    const selected = S.travelStyles.includes(style.id);
    return `<div class="style-card${selected ? ' selected' : ''}"
         data-id="${esc(style.id)}"
         onclick="toggleStyle(this)"
         tabindex="0" role="button"
         aria-pressed="${selected ? 'true' : 'false'}">
      <div class="style-icon">${style.icon}</div>
      <div class="style-label">${esc(t('travel_styles.' + style.id))}</div>
    </div>`;
  }).join('');

  // Replace section contents with single-page form
  section.innerHTML = `
    <div class="ortsreise-form">
      <div class="ortsreise-form-header">
        <h2 class="form-section-title">${esc(t('mode_picker.ortsreise.name'))}</h2>
        <button class="btn btn-link mode-switch-link" type="button" onclick="showModePicker()">${esc(t('form.switch_mode'))}</button>
      </div>

      <div class="form-group">
        <label for="ortsreise-location">${esc(t('form.location_label'))}</label>
        <input type="text" id="ortsreise-location"
          value="${esc(S.locationQuery)}"
          placeholder="${esc(t('form.location_placeholder'))}"
          oninput="S.locationQuery = this.value">
      </div>

      <div class="form-row">
        <div class="form-group">
          <label for="ortsreise-start-date">${esc(t('form.leg_start_date_label'))}</label>
          <input type="date" id="ortsreise-start-date" value="">
        </div>
        <div class="form-group">
          <label for="ortsreise-nights">${esc(t('form.nights_label'))}</label>
          <input type="number" id="ortsreise-nights"
            min="1" max="30"
            value="${S.locationNights}"
            oninput="S.locationNights = parseInt(this.value) || 1">
        </div>
      </div>

      <div class="form-group">
        <label>${esc(t('form.adults_label'))}</label>
        <div class="adults-counter">
          <button type="button" onclick="changeAdults(-1)" aria-label="${esc(t('form.decrease_adults_aria'))}">−</button>
          <span class="adults-count" id="adults-count">${S.adults}</span>
          <button type="button" onclick="changeAdults(1)" aria-label="${esc(t('form.increase_adults_aria'))}">+</button>
        </div>
      </div>

      <div class="form-group">
        <label>${esc(t('form.children_label'))}</label>
        <div id="children-list"></div>
        <button class="btn btn-secondary" type="button" onclick="addChild()" style="margin-top:8px">${esc(t('form.add_child'))}</button>
      </div>

      <div class="form-group">
        <label>${esc(t('form.travel_style_label'))}</label>
        <div class="style-grid" id="ortsreise-style-grid">${stylesHtml}</div>
      </div>

      <div class="form-group">
        <label>${esc(t('form.mandatory_activities_label'))}</label>
        <div class="tag-input-row">
          <input type="text" id="mandatory-tag-input"
            placeholder="${esc(t('form.mandatory_activities_placeholder'))}"
            onkeydown="if(event.key==='Enter'){addTagFromInput();event.preventDefault()}">
          <button class="btn btn-secondary" type="button" onclick="addTagFromInput()">${esc(t('form.add_tag'))}</button>
        </div>
        <div class="tags-container" id="mandatory-tags"></div>
      </div>

      <div class="form-group">
        <label>${esc(t('form.preferred_activities_label'))}</label>
        <div class="tag-input-row">
          <input type="text" id="preferred-tag-input"
            placeholder="${esc(t('form.preferred_activities_placeholder'))}"
            onkeydown="if(event.key==='Enter'){addPreferredTagFromInput();event.preventDefault()}">
          <button class="btn btn-secondary" type="button" onclick="addPreferredTagFromInput()">${esc(t('form.add_tag'))}</button>
        </div>
        <div class="tags-container" id="preferred-tags"></div>
      </div>

      <div class="form-group">
        <label for="travel-description">${esc(t('form.travel_description_label'))}</label>
        <textarea id="travel-description" rows="3"
          placeholder="${esc(t('form.travel_description_placeholder'))}"
          oninput="S.ortsreiseDescription = this.value">${esc(S.ortsreiseDescription)}</textarea>
      </div>

      <div class="form-group">
        <label>${esc(t('form.accommodation_prefs_label'))}</label>
        <label for="acc-pref-0" class="sr-only">${esc(t('form.accommodation_pref1_placeholder'))}</label>
        <input type="text" id="acc-pref-0"
          placeholder="${esc(t('form.accommodation_pref1_placeholder'))}"
          oninput="saveFormToCache()">
        <label for="acc-pref-1" class="sr-only">${esc(t('form.accommodation_pref2_placeholder'))}</label>
        <input type="text" id="acc-pref-1"
          placeholder="${esc(t('form.accommodation_pref2_placeholder'))}"
          oninput="saveFormToCache()" style="margin-top:8px">
        <label for="acc-pref-2" class="sr-only">${esc(t('form.accommodation_pref3_placeholder'))}</label>
        <input type="text" id="acc-pref-2"
          placeholder="${esc(t('form.accommodation_pref3_placeholder'))}"
          oninput="saveFormToCache()" style="margin-top:8px">
        <p class="form-hint">${esc(t('form.accommodation_4th_hint'))}</p>
      </div>

      <button class="btn advanced-toggle" type="button"
              id="ortsreise-advanced-toggle"
              aria-expanded="false"
              onclick="this.setAttribute('aria-expanded',this.getAttribute('aria-expanded')==='true'?'false':'true');document.getElementById('ortsreise-advanced-section').classList.toggle('open')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg>
        <span>${esc(t('form.advanced_toggle'))}</span>
      </button>
      <div class="advanced-section" id="ortsreise-advanced-section">
        <div class="form-group">
          <label for="ortsreise-max-activities">${esc(t('header.max_activities_label'))}</label>
          <select id="ortsreise-max-activities">
            <option value="3">3</option>
            <option value="5" selected>5</option>
            <option value="7">7</option>
            <option value="10">10</option>
          </select>
        </div>
        <div class="form-group">
          <label for="ortsreise-max-restaurants">${esc(t('header.max_restaurants_label'))}</label>
          <select id="ortsreise-max-restaurants">
            <option value="2">2</option>
            <option value="3" selected>3</option>
            <option value="5">5</option>
          </select>
        </div>
        <div class="form-group">
          <label>${esc(t('form.hotel_radius_label'))} <strong id="ortsreise-hotel-radius-display">10</strong> km</label>
          <div class="slider-row">
            <input type="range" id="ortsreise-hotel-radius" min="1" max="50" value="10" step="1"
              oninput="document.getElementById('ortsreise-hotel-radius-display').textContent=this.value">
          </div>
        </div>
        <div class="form-group">
          <label for="ortsreise-log-verbosity">${esc(t('header.log_verbosity_label'))}</label>
          <select id="ortsreise-log-verbosity">
            <option value="minimal">${esc(t('header.log_minimal'))}</option>
            <option value="normal" selected>${esc(t('header.log_normal'))}</option>
            <option value="verbose">${esc(t('header.log_verbose'))}</option>
          </select>
        </div>
      </div>

      <div id="ortsreise-submit-error" class="field-error" style="display:none;margin-bottom:12px"></div>

      <button class="btn cta-secondary" type="button" onclick="submitLocationTrip()">
        ${esc(t('form.plan_trip'))} →
      </button>
    </div>
  `;

  // Populate tag and children containers after innerHTML swap
  renderTags();
  renderPreferredTags();
  renderChildren();

  // Wire Google Places autocomplete if Maps API is ready
  _attachOrtsreiseAutocomplete();
}

/** Persists current Ortsreise form values into the ortsreise sub-object of LS_FORM. */
function saveOrtsreiseToCache() {
  const existing = lsGet(LS_FORM) || {};
  existing.ortsreise = {
    locationQuery:  S.locationQuery,
    locationNights: S.locationNights,
    startDate:      document.getElementById('ortsreise-start-date')?.value || '',
    description:    S.ortsreiseDescription,
    maxActivities:  parseInt(document.getElementById('ortsreise-max-activities')?.value) || 5,
    maxRestaurants: parseInt(document.getElementById('ortsreise-max-restaurants')?.value) || 3,
    hotelRadius:    parseInt(document.getElementById('ortsreise-hotel-radius')?.value) || 10,
    logVerbosity:   document.getElementById('ortsreise-log-verbosity')?.value || 'normal',
  };
  lsSet(LS_FORM, existing);
}

/** Restores persisted Ortsreise values into S and the DOM after renderOrtsreiseForm() builds the HTML. */
function restoreOrtsreiseForm() {
  const cached = lsGet(LS_FORM)?.ortsreise;
  if (!cached) return;

  // Restore state
  if (cached.locationQuery)  { S.locationQuery  = cached.locationQuery; }
  if (cached.locationNights) { S.locationNights = cached.locationNights; }
  if (cached.description)    { S.ortsreiseDescription = cached.description; }

  // Restore DOM — simple value fields
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val != null) el.value = val;
  };

  setVal('ortsreise-location', cached.locationQuery);
  setVal('ortsreise-nights',   cached.locationNights);
  setVal('travel-description', cached.description);
  setVal('ortsreise-max-activities',  cached.maxActivities);
  setVal('ortsreise-max-restaurants', cached.maxRestaurants);
  setVal('ortsreise-log-verbosity',   cached.logVerbosity);

  // Restore range slider + update display label
  if (cached.hotelRadius != null) {
    setVal('ortsreise-hotel-radius', cached.hotelRadius);
    const display = document.getElementById('ortsreise-hotel-radius-display');
    if (display) display.textContent = cached.hotelRadius;
  }

  // Restore start date only if it is today or in the future
  if (cached.startDate) {
    const today = new Date().toISOString().slice(0, 10);
    if (cached.startDate >= today) {
      setVal('ortsreise-start-date', cached.startDate);
    }
  }
}

/** Attaches input/change listeners to all Ortsreise form controls so every edit is auto-saved. */
function _wireOrtsreiseSaveListeners() {
  [
    'ortsreise-location',
    'ortsreise-start-date',
    'ortsreise-nights',
    'travel-description',
    'ortsreise-max-activities',
    'ortsreise-max-restaurants',
    'ortsreise-hotel-radius',
    'ortsreise-log-verbosity',
  ].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input',  saveOrtsreiseToCache);
    el.addEventListener('change', saveOrtsreiseToCache);
  });
}

/** Attaches Google Places autocomplete to the Ortsreise location input. Updates S.locationQuery on selection. */
function _attachOrtsreiseAutocomplete() {
  if (typeof google === 'undefined' || !google.maps || !google.maps.places) return;
  const acOpts = { types: ['(cities)'], fields: ['formatted_address', 'place_id', 'geometry'] };
  const ac = GoogleMaps.attachAutocomplete('ortsreise-location', acOpts);
  if (!ac) return;
  ac.addListener('place_changed', () => {
    const place = ac.getPlace();
    if (place && place.formatted_address) {
      S.locationQuery = place.formatted_address;
      const input = document.getElementById('ortsreise-location');
      if (input) input.value = place.formatted_address;
    }
  });
}

/**
 * Adds `days` days to a YYYY-MM-DD date string and returns the result.
 * @param {string} dateStr - Source date in YYYY-MM-DD format
 * @param {number} days    - Number of days to add
 * @returns {string} Resulting date in YYYY-MM-DD format
 */
function _addDaysToDateStr(dateStr, days) {
  const d = new Date(dateStr);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Validates, builds the Ortsreise TravelRequest payload, and triggers planning via apiPlanLocation(). */
async function submitLocationTrip() {
  const errEl = document.getElementById('ortsreise-submit-error');
  if (errEl) errEl.style.display = 'none';

  const location = S.locationQuery.trim();
  if (!location) {
    if (errEl) { errEl.textContent = t('form.start_location_required'); errEl.style.display = ''; }
    return;
  }

  const startDate = document.getElementById('ortsreise-start-date')?.value || '';
  if (!startDate) {
    if (errEl) { errEl.textContent = t('form.start_date_required'); errEl.style.display = ''; }
    return;
  }

  const nights = Math.max(1, S.locationNights || 7);
  const endDate = _addDaysToDateStr(startDate, nights);

  const payload = {
    legs: [{
      leg_id: 'leg-0',
      mode: 'location',
      start_location: location,
      end_location: '',
      start_date: startDate,
      end_date: endDate,
      via_points: [],
    }],
    total_days: nights,
    adults: S.adults,
    children: S.children,
    travel_styles: S.travelStyles,
    travel_description: document.getElementById('travel-description')?.value || '',
    mandatory_activities: S.mandatoryTags.map(name => ({ name })),
    preferred_activities: S.preferredTags,
    max_activities_per_stop: parseInt(document.getElementById('ortsreise-max-activities')?.value) || 5,
    max_restaurants_per_stop: parseInt(document.getElementById('ortsreise-max-restaurants')?.value) || 3,
    activities_radius_km: 30,
    max_drive_hours_per_day: 0,
    proximity_origin_pct: 0,
    proximity_target_pct: 0,
    min_nights_per_stop: nights,
    max_nights_per_stop: nights,
    accommodation_preferences: getAccPreferences(),
    hotel_radius_km: parseInt(document.getElementById('ortsreise-hotel-radius')?.value) || 10,
    log_verbosity: document.getElementById('ortsreise-log-verbosity')?.value || 'normal',
    language: (typeof getLocale === 'function') ? getLocale() : 'de',
  };

  const submitBtn = document.querySelector('.ortsreise-form .cta-secondary');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="btn-spinner"></span> ' + esc(t('form.planning_trip'));
  }

  try {
    // Pre-init job so SSE can open before Claude starts planning
    const initData = await apiInitJob(payload);
    const jobId = initData.job_id;
    S.jobId = jobId;

    lsSet(LS_ROUTE, { jobId, stops: {}, stopsOrder: [] });
    lsClear(LS_ACCOMMODATIONS);

    // Trigger Ortsreise planning — backend geocodes and jumps straight to accommodation
    progressOverlay.open(t('form.planning_trip') + '…');
    const data = await apiPlanLocation(payload, jobId);
    S.allStops = data.selected_stops || [];

    // Go straight to accommodation phase — no route-building needed for Ortsreise
    showSection('accommodation');
    Router.navigate('/accommodation/' + jobId);
    startAccommodationPhase(data);
    progressOverlay.open(t('accommodation.searching_options', { region: '' }));

    await connectAccommodationSSE(jobId);
    await apiStartAccommodations(jobId);

  } catch (err) {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = t('form.plan_trip') + ' →';
    }
    const msg = err.message || '';
    if (errEl) { errEl.textContent = t('form.trip_planning_error') + ' ' + msg; errEl.style.display = ''; }
    else { alert(t('form.trip_planning_error') + ' ' + msg); }
  }
}
