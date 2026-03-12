'use strict';

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
  window.scrollTo(0, 0);
  // Re-bind click handlers on done steps
  document.querySelectorAll('.step-indicator .step').forEach((el, i) => {
    const stepNum = i + 1;
    if (el.classList.contains('done')) {
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-label', `Zurück zu Schritt ${stepNum}`);
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
      fieldIds.push(`leg-start-${i}`, `leg-end-${i}`, `leg-sdate-${i}`, `leg-edate-${i}`);
    });
    _clearFieldErrors(fieldIds);

    let valid = true;
    for (let i = 0; i < S.legs.length; i++) {
      const leg = S.legs[i];
      if (!leg.start_location) {
        _setFieldError(`leg-start-${i}`, 'Bitte Startort eingeben.');
        if (valid) valid = false;
      }
      if (!leg.end_location) {
        _setFieldError(`leg-end-${i}`, 'Bitte Ziel eingeben.');
        if (valid) valid = false;
      }
      if (!leg.start_date) {
        _setFieldError(`leg-sdate-${i}`, 'Startdatum fehlt.');
        if (valid) valid = false;
      }
      if (!leg.end_date) {
        _setFieldError(`leg-edate-${i}`, 'Enddatum fehlt.');
        if (valid) valid = false;
      }
      if (leg.start_date && leg.end_date && leg.start_date >= leg.end_date) {
        _setFieldError(`leg-edate-${i}`, 'Enddatum muss nach dem Startdatum liegen.');
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
  const formActive = document.getElementById('form-section')?.classList.contains('active');
  const onSummaryStep = S.step === 6;
  // Check if all legs have valid data
  const legsReady = S.legs.length > 0 && S.legs.every(l =>
    l.start_location && l.end_location && l.start_date && l.end_date && l.start_date < l.end_date
  );
  const ready = formActive && legsReady && !onSummaryStep;
  bar.classList.toggle('visible', !!ready);
}

async function quickSubmitTrip() {
  // Validate legs
  const legsReady = S.legs.length > 0 && S.legs.every(l =>
    l.start_location && l.end_location && l.start_date && l.end_date && l.start_date < l.end_date
  );
  if (!legsReady) { alert('Bitte alle Segmente vollständig ausfüllen.'); return; }
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
      if (field === 'start') {
        updateLegField(legIndex, 'start_location', val);
      } else {
        updateLegField(legIndex, 'end_location', val);
      }
    }
    saveFormToCache();
    updateQuickSubmitBar();
  });
}

function updateLegField(index, field, value) {
  S.legs[index][field] = value;
  // Chain: end_location → next leg's start_location
  if (field === 'end_location' && index < S.legs.length - 1) {
    S.legs[index + 1].start_location = value;
    const nextInput = document.getElementById(`leg-start-${index + 1}`);
    if (nextInput) nextInput.value = value;
  }
  saveFormToCache();
  updateQuickSubmitBar();
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
    daysLabel.textContent = `${days} Tag${days !== 1 ? 'e' : ''}`;
  }
  saveFormToCache();
  updateQuickSubmitBar();
}

function renderLegs() {
  const container = document.getElementById("legs-container");
  if (!container) return;
  container.innerHTML = S.legs.map((leg, i) => renderLegCard(leg, i)).join("");

  // Attach autocomplete if Google Maps is ready
  const gmReady = typeof google !== 'undefined' && google.maps && google.maps.places;
  S.legs.forEach((leg, i) => {
    if (gmReady) {
      // First leg: both fields editable; others: only end is editable
      if (i === 0) _attachLegAutocomplete(i, 'start');
      _attachLegAutocomplete(i, 'end');
    }
    if (leg.mode === "explore") setTimeout(() => initZoneMap(i), 50);
  });
}

function renderLegCard(leg, index) {
  const isFirst = index === 0;
  const modeColor = leg.mode === "explore" ? "#e0b840" : "#4a90d9";
  const days = leg.start_date && leg.end_date ? dateDiffDays(leg.start_date, leg.end_date) : 0;
  const canDelete = S.legs.length > 1;

  // Location row
  const startReadonly = !isFirst ? 'readonly tabindex="-1"' : '';
  const startClass = !isFirst ? 'leg-input-chained' : '';
  const locationRow = `
    <div class="leg-location-row">
      <div class="form-group">
        <label for="leg-start-${index}">Von</label>
        <input type="text" id="leg-start-${index}" class="${startClass}"
          value="${esc(leg.start_location)}" placeholder="z.B. Liestal, Schweiz"
          ${startReadonly}
          oninput="updateLegField(${index}, 'start_location', this.value)">
      </div>
      <div class="form-group">
        <label for="leg-end-${index}">Nach</label>
        <input type="text" id="leg-end-${index}"
          value="${esc(leg.end_location)}" placeholder="z.B. Paris, Frankreich"
          oninput="updateLegField(${index}, 'end_location', this.value)">
      </div>
    </div>`;

  // Date row
  const sdateReadonly = !isFirst ? 'readonly tabindex="-1"' : '';
  const sdateClass = !isFirst ? 'leg-input-chained' : '';
  const dateRow = `
    <div class="leg-date-row">
      <div class="form-group">
        <label for="leg-sdate-${index}">Startdatum</label>
        <input type="date" id="leg-sdate-${index}" class="${sdateClass}"
          value="${leg.start_date}" ${sdateReadonly}
          oninput="updateLegDate(${index}, 'start_date', this.value)">
      </div>
      <div class="form-group">
        <label for="leg-edate-${index}">Enddatum</label>
        <input type="date" id="leg-edate-${index}"
          value="${leg.end_date}"
          oninput="updateLegDate(${index}, 'end_date', this.value)">
      </div>
    </div>`;

  const transitContent = leg.mode === "transit" ? `
      <div class="leg-via-points">
          <label class="form-label-sm">Via-Punkte (optional)</label>
          <div class="tag-input" id="via-tags-${index}">
              ${(leg.via_points || []).map(vp => `
                  <span class="tag">${esc(vp.location)}
                      <button onclick="removeViaPoint(${index}, '${esc(vp.location)}')" aria-label="Entfernen">×</button>
                  </span>`).join("")}
              <input type="text" placeholder="Via-Punkt hinzufügen…"
                  onkeydown="handleViaInput(event, ${index})"
                  class="tag-input-field">
          </div>
      </div>` : "";

  const exploreContent = leg.mode === "explore" ? `
      <div class="leg-zone">
          <label class="form-label-sm">Erkundungszone</label>
          <div id="zone-map-${index}" class="zone-map-container" style="height:180px;border-radius:8px;overflow:hidden;border:1px solid #ddd;margin-bottom:8px"></div>
          <div class="zone-label-row">
              <span class="form-label-sm">Zone:</span>
              <input type="text" class="input-sm" id="zone-label-${index}"
                  value="${esc(leg.zone_bbox?.zone_label || '')}"
                  oninput="updateZoneLabel(${index}, this.value)"
                  placeholder="Zone benennen…">
          </div>
      </div>` : "";

  return `
  <div class="leg-card" id="leg-card-${index}" style="border-color:${modeColor}">
      <div class="leg-card-header" style="background:${leg.mode === 'explore' ? '#fdf8e8' : '#f5f5f5'}">
          <div class="leg-badge" style="background:${modeColor}">${index + 1}</div>
          <span class="leg-days-label" id="leg-days-${index}">${days > 0 ? `${days} Tag${days !== 1 ? 'e' : ''}` : ''}</span>
          <div class="leg-controls">
              <div class="mode-toggle">
                  <button class="mode-btn ${leg.mode === 'transit' ? 'active' : ''}"
                      onclick="setLegMode(${index}, 'transit')" style="border-color:${modeColor}">Transit</button>
                  <button class="mode-btn ${leg.mode === 'explore' ? 'active' : ''}"
                      onclick="setLegMode(${index}, 'explore')" style="border-color:${modeColor}">Erkunden</button>
              </div>
              ${canDelete ? `<button class="leg-delete-btn" onclick="removeLeg(${index})" aria-label="Segment entfernen">×</button>` : ""}
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
      alert('Das Segment hat zu wenige Tage zum Aufteilen. Bitte zuerst das Enddatum anpassen.');
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
  if (mode === "explore" && !S.legs[index].zone_bbox) {
    S.legs[index].zone_bbox = null;
  }
  renderLegs();
  if (mode === "explore") {
    setTimeout(() => initZoneMap(index), 50);
  }
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

function updateZoneLabel(legIndex, label) {
  if (S.legs[legIndex].zone_bbox) {
    S.legs[legIndex].zone_bbox.zone_label = label;
  } else {
    // Store label for when bbox is drawn on the map — don't create invalid zero-coords bbox
    S.legs[legIndex]._pending_zone_label = label;
  }
}

function initZoneMap(legIndex) {
  const containerId = `zone-map-${legIndex}`;
  const container = document.getElementById(containerId);
  if (!container || container._leaflet_id) return; // already initialized

  const leg = S.legs[legIndex];
  const map = L.map(containerId).setView([48.0, 10.0], 4);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap"
  }).addTo(map);

  let rect = null;

  // Restore existing bbox if present
  if (leg.zone_bbox && leg.zone_bbox.north) {
    const bounds = [[leg.zone_bbox.south, leg.zone_bbox.west],
                    [leg.zone_bbox.north, leg.zone_bbox.east]];
    rect = L.rectangle(bounds, { color: "#e0b840", weight: 2, fillOpacity: 0.15 }).addTo(map);
    map.fitBounds(bounds);
  }

  // Draw bbox on drag using Leaflet.draw
  if (typeof L.Draw !== 'undefined') {
    const drawControl = new L.Draw.Rectangle(map, { shapeOptions: { color: "#e0b840" } });
    map.on(L.Draw.Event.CREATED, async (e) => {
      if (rect) rect.remove();
      rect = e.layer.addTo(map);
      const b = e.layer.getBounds();
      const bbox = {
        north: b.getNorth(), south: b.getSouth(),
        east: b.getEast(), west: b.getWest(),
        zone_label: S.legs[legIndex].zone_bbox?.zone_label || S.legs[legIndex]._pending_zone_label || ""
      };
      S.legs[legIndex].zone_bbox = bbox;
      // Auto-geocode zone label
      const center = b.getCenter();
      const label = await geocodeZoneLabel(center.lat, center.lng);
      if (label) {
        S.legs[legIndex].zone_bbox.zone_label = label;
        const labelInput = document.getElementById(`zone-label-${legIndex}`);
        if (labelInput) labelInput.value = label;
      }
    });
    drawControl.enable();
  }
}

async function geocodeZoneLabel(lat, lon) {
  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
      { headers: { "Accept-Language": "de" } }
    );
    const data = await resp.json();
    return data.address?.country || data.address?.state || null;
  } catch {
    return null;
  }
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
      <div class="style-label">${esc(style.label)}</div>
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
    btn.title = 'Entfernen';
    btn.setAttribute('aria-label', `Tag '${tag}' entfernen`);
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
      <button class="btn-icon btn-danger" onclick="removeChild(${i})" aria-label="Kind ${i + 1} entfernen">×</button>
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
    errSpan.textContent = valid ? '' : '— muss 100% sein';
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

function buildPayload() {
  const firstLeg = S.legs[0] || {};
  const lastLeg = S.legs[S.legs.length - 1] || {};
  const sd = firstLeg.start_date || '';
  const ed = lastLeg.end_date || '';
  const msPerDay = 86400000;
  const total_days = sd && ed
    ? Math.max(1, Math.round((new Date(ed) - new Date(sd)) / msPerDay))
    : 7;

  // Clean legs for payload: strip internal fields, ensure explore legs have valid zone_bbox
  const cleanLegs = S.legs.map(leg => {
    const { _pending_zone_label, ...clean } = leg;
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
    preferred_activities: [],
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
  const legsDisplay = S.legs.map(l => esc(l.start_location) + ' → ' + esc(l.end_location) + ' (' + l.mode + ')').join(' | ');
  el.innerHTML = `
    <div class="summary-grid">
      <div class="summary-item"><span class="summary-label">Start</span><span>${esc(firstLeg.start_location)}</span></div>
      <div class="summary-item"><span class="summary-label">Ziel</span><span>${esc(lastLeg.end_location)}</span></div>
      <div class="summary-item"><span class="summary-label">Datum</span><span>${formatDate(firstLeg.start_date)} – ${formatDate(lastLeg.end_date)} (${p.total_days} Tage)</span></div>
      <div class="summary-item"><span class="summary-label">Reisende</span><span>${p.adults} Erwachsene${p.children.length ? ', ' + p.children.length + ' Kinder' : ''}</span></div>
      <div class="summary-item"><span class="summary-label">Stile</span><span>${p.travel_styles.map(s => TRAVEL_STYLES.find(t => t.id === s)?.label || s).join(', ') || '–'}</span></div>
      <div class="summary-item"><span class="summary-label">Budget</span><span>CHF ${(p.budget_chf || 0).toLocaleString('de-CH')} (Unterkunft ${p.budget_accommodation_pct}% / Essen ${p.budget_food_pct}% / Aktivitäten ${p.budget_activities_pct}%)</span></div>
      <div class="summary-item"><span class="summary-label">Max. Fahrzeit</span><span>${p.max_drive_hours_per_day}h/Tag</span></div>
      ${p.mandatory_activities.length ? `<div class="summary-item"><span class="summary-label">Pflichtaktivitäten</span><span>${p.mandatory_activities.map(a => esc(a.name)).join(', ')}</span></div>` : ''}
      <div class="summary-item"><span class="summary-label">Segmente</span><span>${legsDisplay}</span></div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

async function submitTrip() {
  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Plane Reise…';

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
    _showSkeletonCards();
    progressOverlay.open('Zwischenstopps werden gesucht…');
    openRouteSSE(preJobId);

    // 3. Trigger actual planning (Claude + OSRM); SSE delivers options progressively
    const data = await apiPlanTrip(payload, preJobId);

    S.currentOptions = data.options || [];
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
  lsSet(LS_FORM, { ...p, travelStyles: S.travelStyles, children: S.children, mandatoryTags: S.mandatoryTags });
  updateQuickSubmitBar();
}

function setupFormAutoSave() {
  document.querySelectorAll('#form-section input, #form-section select, #form-section textarea')
    .forEach(el => { el.addEventListener('change', saveFormToCache); });
  // Settings menu lives outside #form-section — attach separately
  ['max-activities', 'max-restaurants'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', saveFormToCache);
  });
}

function restoreFormFromCache() {
  const cached = lsGet(LS_FORM);
  if (!cached) return;

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

  // Hide resume banner
  document.getElementById('resume-banner').style.display = 'none';

  // Return to form step 1
  goToStep(1);
  showSection('form-section');
}

