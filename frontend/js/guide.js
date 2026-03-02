'use strict';

let activeTab = 'overview';

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
    case 'overview':   content.innerHTML = renderOverview(plan);  break;
    case 'stops':      content.innerHTML = renderStops(plan);     break;
    case 'dayplan':    content.innerHTML = renderDayPlan(plan);   break;
    case 'budget':     content.innerHTML = renderBudget(plan);    break;
    default:           content.innerHTML = renderOverview(plan);
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
        ${mapUrl ? `<a href="${esc(mapUrl)}" target="_blank" class="btn btn-secondary">
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
    </div>
  `;
}

function renderStops(plan) {
  const stops = plan.stops || [];
  return `
    <div class="stops-section">
      ${stops.map(stop => {
        const flag = FLAGS[stop.country] || '';
        const acc  = stop.accommodation || {};
        const acts = stop.top_activities || [];
        const rests = stop.restaurants || [];

        return `
          <div class="stop-card">
            <div class="stop-header">
              <div class="stop-number">Stop ${stop.id}</div>
              <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
              <div class="stop-meta">
                Tag ${stop.arrival_day} · ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
                ${stop.drive_hours_from_prev > 0 ? ` · ${stop.drive_hours_from_prev}h Fahrt` : ''}
                ${stop.drive_km_from_prev > 0 ? ` · ${stop.drive_km_from_prev} km` : ''}
              </div>
              ${stop.google_maps_url ? `<a href="${esc(stop.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
            ${buildImageGallery(stop.image_overview, stop.image_mood, stop.image_customer, esc(stop.region))}

            ${acc.name ? `
              <div class="stop-accommodation">
                <h4>Unterkunft</h4>
                ${buildImageGallery(acc.image_overview, acc.image_mood, acc.image_customer, esc(acc.name))}
                <div class="acc-summary">
                  <strong>${esc(acc.name)}</strong>
                  <span class="acc-type-tag">${esc(acc.type || '')}</span>
                  <span class="acc-price-tag">CHF ${(acc.total_price_chf || 0).toLocaleString('de-CH')}</span>
                  ${acc.booking_url ? `<a href="${esc(acc.booking_url)}" target="_blank" class="booking-link">Buchen</a>` : ''}
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
                        ${act.google_maps_url ? `<a href="${esc(act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

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
          </div>
        `;
      }).join('')}
    </div>
  `;
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
            <a href="${esc(dp.google_maps_route_url)}" target="_blank" class="btn btn-sm">Route in Maps</a>
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
