'use strict';

let activeTab = 'overview';
let _guideMap = null;
let _guideMapMarkers = [];
let _guideMapLine = null;

function showTravelGuide(plan) {
  S.result = plan;
  renderGuide(plan, activeTab);
}

function renderGuide(plan, tab) {
  activeTab = tab || 'overview';

  // Update tab buttons
  document.querySelectorAll('.guide-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === activeTab);
  });

  const content = document.getElementById('guide-content');
  if (!content) return;

  switch (activeTab) {
    case 'overview':
      content.innerHTML = renderOverview(plan);
      _initGuideMap(plan);
      break;
    case 'stops':      content.innerHTML = renderStops(plan);     break;
    case 'budget':     content.innerHTML = renderBudget(plan);    break;
    default:
      content.innerHTML = renderOverview(plan);
      _initGuideMap(plan);
  }
}

function switchGuideTab(tab) {
  renderGuide(S.result, tab);
}

function renderOverview(plan) {
  const stops = plan.stops || [];
  const cost  = plan.cost_estimate || {};
  const mapUrl = plan.google_maps_overview_url || '';

  return `
    <div class="overview-section">
      <div class="overview-hero">
        <h2>Reise: ${esc(plan.start_location)} → ${esc(stops[stops.length - 1]?.region || '')}</h2>
        <p>${stops.length} Stops · ${plan.day_plans?.length || 0} Tage</p>
        ${mapUrl ? `<a href="${safeUrl(mapUrl)}" target="_blank" class="btn btn-secondary">
          Google Maps öffnen
        </a>` : ''}
      </div>

      <div class="overview-stats">
        <div class="stat-card">
          <div class="stat-value">${stops.length}</div>
          <div class="stat-label">Stops</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${plan.day_plans?.length || 0}</div>
          <div class="stat-label">Tage</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">CHF ${typeof cost.total_chf === 'number' ? cost.total_chf.toLocaleString('de-CH') : '–'}</div>
          <div class="stat-label">Gesamtkosten</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">CHF ${typeof cost.budget_remaining_chf === 'number' ? cost.budget_remaining_chf.toLocaleString('de-CH') : '–'}</div>
          <div class="stat-label">Rest-Budget</div>
        </div>
      </div>

      <div class="overview-route">
        <h3>Route</h3>
        <div class="route-line">
          <div class="route-point start">${esc(plan.start_location)}</div>
          ${stops.map(s => `
            <div class="route-arrow">→</div>
            <div class="route-point">
              ${FLAGS[s.country] || ''} ${esc(s.region)}
              <small>${s.nights} N.</small>
            </div>
          `).join('')}
        </div>
      </div>

      <div id="guide-map"></div>
    </div>
  `;
}

function renderProse(text) {
  if (!text) return '';
  return text.split(/\n\n+/).map(p => `<p>${esc(p.trim())}</p>`).join('');
}

function renderTravelGuide(guide) {
  if (!guide) return '';
  const sections = [
    { key: 'history_culture',  label: 'Geschichte & Kultur' },
    { key: 'food_specialties', label: 'Lokale Spezialitäten' },
    { key: 'local_tips',       label: 'Praktische Tipps' },
    { key: 'insider_gems',     label: 'Insider-Tipps' },
    { key: 'best_time_to_visit', label: 'Beste Reisezeit' },
  ];
  return `
    <div class="reisefuehrer-section">
      <h4 class="reisefuehrer-title">Reiseführer</h4>
      <div class="guide-intro">${renderProse(guide.intro_narrative)}</div>
      ${sections.map(s => guide[s.key] ? `
        <details class="guide-collapse">
          <summary>${esc(s.label)}</summary>
          <div class="guide-collapse-body">${renderProse(guide[s.key])}</div>
        </details>
      ` : '').join('')}
    </div>
  `;
}

function renderFurtherActivities(activities) {
  if (!activities || !activities.length) return '';
  return `
    <div class="further-activities-section">
      <h4>Weitere Empfehlungen im Umkreis</h4>
      <div class="further-activities-list">
        ${activities.map(act => `
          <div class="further-activity-item">
            <div class="further-activity-content">
              <strong>${esc(act.name)}</strong>
              <p>${esc(act.description)}</p>
              <div class="activity-meta">
                ${act.duration_hours}h
                ${act.price_chf > 0 ? ` · CHF ${act.price_chf}` : ' · kostenlos'}
                ${act.suitable_for_children ? ' · familienfreundlich' : ''}
              </div>
              ${act.google_maps_url ? `<a href="${safeUrl(act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderDayTimeBlocks(dayPlan) {
  const blocks = dayPlan.time_blocks || [];
  if (!blocks.length) return '';

  const typeIcon = {
    drive:    '🚗',
    activity: '🎭',
    meal:     '🍽️',
    break:    '☕',
    check_in: '🏨',
  };

  return `
    <div class="day-timeblocks">
      <div class="timeblocks-timeline">
        ${blocks.map(tb => `
          <div class="time-block type-${esc(tb.activity_type)}">
            <div class="time-block-time">${esc(tb.time)}</div>
            <div class="time-block-dot"></div>
            <div class="time-block-content">
              <div class="time-block-header">
                <span class="time-block-icon">${typeIcon[tb.activity_type] || '📍'}</span>
                <strong>${esc(tb.title)}</strong>
                <span class="time-block-duration">${tb.duration_minutes} min</span>
              </div>
              ${tb.location ? `<div class="time-block-location">📍 ${esc(tb.location)}</div>` : ''}
              ${tb.description ? `<p class="time-block-desc">${esc(tb.description)}</p>` : ''}
              ${tb.price_chf ? `<span class="time-block-price">CHF ${tb.price_chf}</span>` : ''}
              <div class="time-block-links">
                ${tb.google_search_url ? `<a href="${safeUrl(tb.google_search_url)}" target="_blank" class="tb-link">Google Suche</a>` : ''}
                ${tb.google_maps_url ? `<a href="${safeUrl(tb.google_maps_url)}" target="_blank" class="tb-link maps-link">Maps</a>` : ''}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderStops(plan) {
  const stops = plan.stops || [];
  const dayPlans = plan.day_plans || [];

  return `
    <div class="stops-section">
      ${stops.map(stop => {
        const flag = FLAGS[stop.country] || '';
        const acc  = stop.accommodation || {};
        const acts = stop.top_activities || [];
        const rests = stop.restaurants || [];
        const further = stop.further_activities || [];

        // Day plans that fall within this stop's nights
        const arrivalDay = stop.arrival_day || 1;
        const stopDays = dayPlans.filter(d =>
          d.day >= arrivalDay && d.day < arrivalDay + (stop.nights || 1)
        );

        return `
          <div class="stop-card" id="guide-stop-${stop.id}">
            <div class="stop-header">
              <div class="stop-number">Stop ${stop.id}</div>
              <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
              <div class="stop-meta">
                Tag ${stop.arrival_day} · ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
                ${stop.drive_hours_from_prev > 0 ? ` · ${stop.drive_hours_from_prev}h Fahrt` : ''}
                ${stop.drive_km_from_prev > 0 ? ` · ${stop.drive_km_from_prev} km` : ''}
              </div>
              ${stop.google_maps_url ? `<a href="${safeUrl(stop.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
            ${buildImageGallery(stop.image_overview, stop.image_mood, stop.image_customer, esc(stop.region))}

            ${renderTravelGuide(stop.travel_guide)}

            ${acc.name ? `
              <div class="stop-accommodation">
                <h4>Unterkunft</h4>
                ${buildImageGallery(acc.image_overview, acc.image_mood, acc.image_customer, esc(acc.name))}
                <div class="acc-summary">
                  <strong>${esc(acc.name)}</strong>
                  ${acc.is_geheimtipp ? `<span class="geheimtipp-badge">Geheimtipp</span>` : ''}
                  <span class="acc-type-tag">${esc(acc.type || '')}</span>
                  <span class="acc-price-tag">ca. CHF ${(acc.total_price_chf || 0).toLocaleString('de-CH')}</span>
                </div>
                ${acc.description ? `<div class="acc-guide-description">${highlightMustHaves(acc.description, acc.matched_must_haves || [])}</div>` : ''}
                <div class="acc-guide-links">
                  ${acc.booking_url ? `<a href="${safeUrl(acc.booking_url)}" target="_blank" class="acc-booking-link">Bei Booking.com anschauen →</a>` : ''}
                  ${acc.booking_search_url ? `<a href="${safeUrl(acc.booking_search_url)}" target="_blank" class="acc-booking-link acc-booking-search">Bei Booking.com suchen →</a>` : ''}
                  ${acc.hotel_website_url ? `<a href="${safeUrl(acc.hotel_website_url)}" target="_blank" class="acc-website-link">Hotelwebseite →</a>` : ''}
                </div>
              </div>
            ` : ''}

            ${acts.length ? `
              <div class="stop-activities">
                <h4>Aktivitäten</h4>
                <div class="activities-grid">
                  ${acts.map(act => `
                    <div class="activity-card">
                      ${buildImageGallery(act.image_overview, act.image_mood, act.image_customer, esc(act.name))}
                      <div class="activity-content">
                        <strong>${esc(act.name)}</strong>
                        <p>${esc(act.description)}</p>
                        <div class="activity-meta">
                          ${act.duration_hours}h
                          ${act.price_chf > 0 ? ` · CHF ${act.price_chf}` : ' · kostenlos'}
                          ${act.suitable_for_children ? ' · familienfreundlich' : ''}
                        </div>
                        ${act.google_maps_url ? `<a href="${safeUrl(act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            ${renderFurtherActivities(further)}

            ${rests.length ? `
              <div class="stop-restaurants">
                <h4>Restaurants</h4>
                <div class="restaurants-list">
                  ${rests.map(r => `
                    <div class="restaurant-item">
                      ${buildImageGallery(r.image_overview, r.image_mood, r.image_customer, esc(r.name))}
                      <div style="padding: 10px">
                        <strong>${esc(r.name)}</strong>
                        <span class="cuisine-tag">${esc(r.cuisine)}</span>
                        <span class="price-range">${esc(r.price_range)}</span>
                        ${r.family_friendly ? '<span class="family-tag">Familienfreundlich</span>' : ''}
                        ${r.notes ? `<p class="rest-notes">${esc(r.notes)}</p>` : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            ${stopDays.length ? `
              <div class="stop-day-examples">
                <h4>Tagesbeispiele</h4>
                ${stopDays.map(dp => `
                  <details class="day-example-collapse" open>
                    <summary>
                      <span class="day-example-label">Tag ${dp.day}${dp.date ? ' · ' + esc(dp.date) : ''}</span>
                      <span class="day-example-title">${esc(dp.title)}</span>
                    </summary>
                    <div class="day-example-body">
                      <p class="day-example-desc">${esc(dp.description)}</p>
                      ${renderDayTimeBlocks(dp)}
                    </div>
                  </details>
                `).join('')}
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function _scrollToGuideStop(stopId) {
  switchGuideTab('stops');
  // After tab switch the DOM is re-rendered; use rAF to wait one frame
  requestAnimationFrame(() => {
    document.getElementById(`guide-stop-${stopId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function _initGuideMap(plan) {
  const mapEl = document.getElementById('guide-map');
  if (!mapEl) return;

  const stops = plan.stops || [];

  // Destroy old map instance if the element was replaced by innerHTML
  if (_guideMap) {
    _guideMap.remove();
    _guideMap = null;
    _guideMapMarkers = [];
    _guideMapLine = null;
  }

  _guideMap = L.map('guide-map').setView([47, 8], 6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(_guideMap);

  const bounds = [];

  // Start pin (green S)
  if (plan.start_lat && plan.start_lng) {
    const icon = L.divIcon({
      className: '',
      html: `<div class="map-marker-anchor start-pin">S</div>`,
      iconSize: [28, 28], iconAnchor: [14, 14],
    });
    L.marker([plan.start_lat, plan.start_lng], { icon })
      .bindPopup(`<b>Start: ${esc(plan.start_location)}</b>`)
      .addTo(_guideMap);
    bounds.push([plan.start_lat, plan.start_lng]);
  }

  // Stop pins — last stop gets red Z, others blue numbered
  // Collect ordered route points for polyline: start → stops in sequence
  const routePoints = [];
  if (plan.start_lat && plan.start_lng) {
    routePoints.push([plan.start_lat, plan.start_lng]);
  }

  stops.forEach((stop, i) => {
    const sLat = stop.lat;
    const sLng = stop.lng;
    if (!sLat || !sLng) return;

    const isLast = i === stops.length - 1;
    const icon = L.divIcon({
      className: '',
      html: isLast
        ? `<div class="map-marker-anchor target-pin">Z</div>`
        : `<div class="map-marker-num">${stop.id}</div>`,
      iconSize: [28, 28], iconAnchor: [14, 14],
    });
    const marker = L.marker([sLat, sLng], { icon })
      .bindPopup(`<b>${FLAGS[stop.country] || ''} ${stop.region}</b><br>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}`)
      .addTo(_guideMap);
    marker.on('click', () => _scrollToGuideStop(stop.id));
    _guideMapMarkers.push(marker);
    bounds.push([sLat, sLng]);
    routePoints.push([sLat, sLng]);
  });

  // Draw solid route polyline through all points in order
  if (routePoints.length >= 2) {
    _guideMapLine = L.polyline(routePoints, { color: '#0071e3', weight: 3, opacity: 0.8 }).addTo(_guideMap);
  }

  if (bounds.length > 0) {
    _guideMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 });
  }

  setTimeout(() => { if (_guideMap) _guideMap.invalidateSize(); }, 100);
}

function renderDayPlan(plan) {
  const dayPlans = plan.day_plans || [];
  return `
    <div class="dayplan-section">
      ${dayPlans.map(dp => `
        <div class="day-card type-${esc(dp.type)}">
          <div class="day-header">
            <div class="day-number">Tag ${dp.day}</div>
            ${dp.date ? `<div class="day-date">${esc(dp.date)}</div>` : ''}
            <div class="day-type-badge">${esc(dp.type)}</div>
          </div>
          <h3>${esc(dp.title)}</h3>
          <p>${esc(dp.description)}</p>
          ${dp.stops_on_route.length ? `
            <div class="day-route">
              <strong>Route:</strong> ${dp.stops_on_route.map(s => esc(s)).join(' → ')}
            </div>
          ` : ''}
          ${dp.google_maps_route_url ? `
            <a href="${safeUrl(dp.google_maps_route_url)}" target="_blank" class="btn btn-sm">Route in Maps</a>
          ` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function renderBudget(plan) {
  const cost = plan.cost_estimate || {};
  const total = typeof cost.total_chf === 'number' ? cost.total_chf : 0;
  const acc   = typeof cost.accommodations_chf === 'number' ? cost.accommodations_chf : 0;
  const act   = typeof cost.activities_chf === 'number' ? cost.activities_chf : 0;
  const food  = typeof cost.food_chf === 'number' ? cost.food_chf : 0;
  const fuel  = typeof cost.fuel_chf === 'number' ? cost.fuel_chf : 0;
  const ferry = typeof cost.ferries_chf === 'number' ? cost.ferries_chf : 0;
  const rem   = typeof cost.budget_remaining_chf === 'number' ? cost.budget_remaining_chf : 0;

  const items = [
    { label: 'Unterkunft',  value: acc,   color: '#0071e3' },
    { label: 'Aktivitäten', value: act,   color: '#34c759' },
    { label: 'Verpflegung', value: food,  color: '#ff9f0a' },
    { label: 'Treibstoff',  value: fuel,  color: '#ff3b30' },
    { label: 'Fähren',      value: ferry, color: '#5856d6' },
  ];

  return `
    <div class="budget-section">
      <div class="budget-total">
        <div class="budget-amount">CHF ${total.toLocaleString('de-CH')}</div>
        <div class="budget-label">Gesamtkosten</div>
      </div>

      <div class="budget-breakdown">
        ${items.filter(it => it.value > 0).map(it => {
          const pct = total > 0 ? (it.value / total * 100).toFixed(1) : 0;
          return `
            <div class="budget-row">
              <div class="budget-row-label">${esc(it.label)}</div>
              <div class="budget-bar-wrap">
                <div class="budget-bar" style="width: ${pct}%; background: ${it.color}"></div>
              </div>
              <div class="budget-row-amount">CHF ${it.value.toLocaleString('de-CH')}</div>
              <div class="budget-row-pct">${pct}%</div>
            </div>
          `;
        }).join('')}
      </div>

      <div class="budget-remaining ${rem >= 0 ? 'positive' : 'negative'}">
        <span>Verbleibendes Budget:</span>
        <strong>CHF ${rem.toLocaleString('de-CH')}</strong>
      </div>

      <div class="output-actions">
        <h3>Reiseplan exportieren</h3>
        <button class="btn btn-primary" onclick="generateOutput('pdf')">PDF herunterladen</button>
        <button class="btn btn-secondary" onclick="generateOutput('pptx')">PowerPoint herunterladen</button>
      </div>
    </div>
  `;
}

async function generateOutput(type) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Wird erstellt…';

  try {
    const blob = await apiGenerateOutput(S.jobId, type);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reiseplan_${S.jobId}.${type}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('Fehler beim Erstellen: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = type === 'pdf' ? 'PDF herunterladen' : 'PowerPoint herunterladen';
  }
}

function loadGuideFromCache() {
  const saved = lsGet(LS_RESULT);
  if (saved && saved.plan) {
    S.result = saved.plan;
    S.jobId = saved.jobId;
    showTravelGuide(saved.plan);
    showSection('travel-guide');
  }
}

async function replanCurrentTravel() {
  const plan = S.result;
  if (!plan) return;

  // Find the saved travel ID from the plan's job_id in travel DB
  // We pass the plan directly to the replan endpoint via a helper
  const savedId = plan._saved_travel_id || null;

  if (!savedId) {
    alert('Diese Reise ist nicht in «Meine Reisen» gespeichert. Bitte erst speichern.');
    return;
  }

  if (!confirm('Reiseführer und stündliche Tagespläne neu generieren?\n\nRoute und Unterkünfte bleiben erhalten.')) return;

  const btn = document.getElementById('replan-current-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Wird gestartet…'; }

  try {
    const { job_id } = await apiReplanTravel(savedId);
    S.jobId = job_id;
    showSection('progress');
    document.getElementById('progress-error').style.display = 'none';
    const statusEl = document.getElementById('progress-agent-status');
    if (statusEl) statusEl.textContent = 'Reiseführer und Tagespläne werden neu berechnet…';

    const source = openSSE(job_id, {
      job_complete: (data) => {
        source.close();
        S.result = data;
        lsSet(LS_RESULT, { jobId: data.job_id || job_id, savedAt: new Date().toISOString(), plan: data });
        showTravelGuide(data);
        showSection('travel-guide');
      },
      job_error: (data) => {
        source.close();
        const errEl = document.getElementById('progress-error');
        if (errEl) { errEl.textContent = 'Fehler: ' + (data.error || 'Unbekannter Fehler'); errEl.style.display = ''; }
        showSection('progress');
      },
      debug_log: (data) => {
        if (statusEl && data.message) statusEl.textContent = data.message;
        if (typeof appendProgressLine === 'function') appendProgressLine(data);
      },
    });
  } catch (err) {
    alert('Fehler: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Neu berechnen'; }
  }
}
