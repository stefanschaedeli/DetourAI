'use strict';

let activeTab = 'overview';
let _guideMarkers = [];
let _guidePolyline = null;

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
    case 'stops':
      content.innerHTML = renderStops(plan);
      requestAnimationFrame(() => {
        _initStopsSidebar();
        try { _lazyLoadStopImages(plan); } catch (e) { console.error('Stop images:', e); }
      });
      break;
    case 'calendar':
      content.innerHTML = renderCalendar(plan);
      _initCalendarClicks(plan);
      break;
    case 'budget':     content.innerHTML = renderBudget(plan);    break;
    default:
      content.innerHTML = renderOverview(plan);
      _initGuideMap(plan);
  }

  // Fade-in animation on tab switch
  content.style.opacity = '0';
  content.style.transform = 'translateY(6px)';
  requestAnimationFrame(() => {
    content.style.transition = 'opacity .2s ease, transform .2s ease';
    content.style.opacity = '1';
    content.style.transform = 'translateY(0)';
  });
}

function switchGuideTab(tab) {
  renderGuide(S.result, tab);
  if (S.result && S.result._saved_travel_id) {
    const title = S.result.custom_name || S.result.title || '';
    const base = Router.travelPath(S.result._saved_travel_id, title);
    const path = (tab && tab !== 'overview') ? base + '/' + tab : base;
    Router.navigate(path, { replace: true, skipDispatch: true });
  }
}

// Called by router only — render tab without URL update
function activateGuideTab(tab) {
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

      ${renderTripAnalysis(plan.trip_analysis, plan.request)}
    </div>
  `;
}

// Highlight requirement keywords (from plan.request) in an already-escaped string
function _highlightReqKeywords(escapedText, keywords) {
  let t = escapedText;
  keywords.forEach(kw => {
    if (!kw) return;
    const safe = esc(kw);
    const re = new RegExp(safe.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    t = t.replace(re, m => `<strong class="req-keyword">${m}</strong>`);
  });
  return t;
}

// Build a flat list of keywords from plan.request that the user explicitly set
function _extractReqKeywords(req) {
  if (!req) return [];
  const kws = [];
  (req.travel_styles || []).forEach(s => {
    const label = (TRAVEL_STYLES.find(t => t.id === s) || {}).label;
    if (label) kws.push(label);
  });
  (req.accommodation_preferences || []).forEach(k => kws.push(k));
  (req.mandatory_activities || []).forEach(a => kws.push(typeof a === 'string' ? a : a.name));
  (req.preferred_activities || []).forEach(k => kws.push(k));
  if (req.main_destination) kws.push(req.main_destination);
  if (req.destination)      kws.push(req.destination);
  return kws.filter(Boolean);
}

// Render inline requirement tags from the original request
function _renderReqTags(req) {
  if (!req) return '';
  const tags = [];

  // Route
  if (req.start_location) tags.push({ label: req.start_location, cls: 'req-tag-route' });
  const dest = req.main_destination || req.destination;
  if (dest) tags.push({ label: dest, cls: 'req-tag-route' });

  // Dates & duration
  const days = req.total_days || req.duration_days;
  if (days) tags.push({ label: `${days} Tage`, cls: 'req-tag-meta' });
  if (req.adults) {
    const children = (req.children || []).length;
    const pax = children > 0
      ? `${req.adults} Erw. + ${children} Kind${children > 1 ? 'er' : ''}`
      : `${req.adults} Erwachsene`;
    tags.push({ label: pax, cls: 'req-tag-meta' });
  }
  if (req.budget_chf) tags.push({ label: `CHF ${Number(req.budget_chf).toLocaleString('de-CH')}`, cls: 'req-tag-budget' });
  if (req.max_drive_hours_per_day) tags.push({ label: `Max. ${req.max_drive_hours_per_day}h Fahrt/Tag`, cls: 'req-tag-meta' });

  // Styles
  (req.travel_styles || []).forEach(s => {
    const label = (TRAVEL_STYLES.find(t => t.id === s) || {}).label || s;
    tags.push({ label, cls: 'req-tag-style' });
  });

  // Accommodation preferences
  (req.accommodation_preferences || []).forEach(k => tags.push({ label: k, cls: 'req-tag-acc' }));

  // Mandatory activities
  (req.mandatory_activities || []).forEach(a => {
    const name = typeof a === 'string' ? a : a.name;
    tags.push({ label: name, cls: 'req-tag-activity' });
  });

  if (!tags.length) return '';
  return `<div class="req-tags">${tags.map(t => `<span class="req-tag ${t.cls}">${esc(t.label)}</span>`).join('')}</div>`;
}

function renderTripAnalysis(analysis, req) {
  if (!analysis) return '';

  const score = analysis.requirements_match_score || 0;
  const scoreColor = score >= 8 ? '#22C55E' : score >= 5 ? '#F59E0B' : '#EF4444';
  const scoreLabel = score >= 8 ? 'Sehr gut' : score >= 6 ? 'Gut' : score >= 4 ? 'Befriedigend' : 'Verbesserungsbedarf';
  const pct = Math.round(score / 10 * 100);

  const keywords = _extractReqKeywords(req);

  const impactLabel = { high: 'Hoch', medium: 'Mittel', low: 'Niedrig' };
  const impactClass = { high: 'impact-high', medium: 'impact-medium', low: 'impact-low' };

  // Use keyword-highlighting instead of plain esc for prose fields
  const summaryHtml    = _highlightReqKeywords(esc(analysis.settings_summary || ''), keywords);
  const analysisHtml   = _highlightReqKeywords(esc(analysis.requirements_analysis || ''), keywords);

  const strengths  = (analysis.strengths || []).map(s =>
    `<li>${_highlightReqKeywords(esc(s), keywords)}</li>`).join('');
  const weaknesses = (analysis.weaknesses || []).map(w =>
    `<li>${_highlightReqKeywords(esc(w), keywords)}</li>`).join('');

  const suggestions = (analysis.improvement_suggestions || []).map(s => `
    <div class="suggestion-item">
      <div class="suggestion-header">
        <strong>${esc(s.title)}</strong>
        <span class="impact-badge ${impactClass[s.impact] || ''}">${impactLabel[s.impact] || esc(s.impact)}</span>
      </div>
      <p>${_highlightReqKeywords(esc(s.description), keywords)}</p>
    </div>
  `).join('');

  return `
    <div class="trip-analysis">
      <div class="trip-analysis-header">
        <h3 class="trip-analysis-title">Reise-Analyse</h3>
        <div class="ta-score-chip" style="background:${scoreColor}22; color:${scoreColor}; border-color:${scoreColor}55">
          <span class="ta-score-num">${score}</span><span class="ta-score-denom">/10</span>
          <span class="ta-score-label">${scoreLabel}</span>
        </div>
      </div>

      <div class="trip-analysis-card">
        <h4>Ihre Reiseanforderungen</h4>
        ${_renderReqTags(req)}
        ${analysis.settings_summary ? `<p class="trip-analysis-text ta-summary">${summaryHtml}</p>` : ''}
      </div>

      <div class="trip-analysis-card ta-card-score">
        <h4>Anforderungserfüllung</h4>
        <div class="score-bar-wrap">
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:${pct}%; background:${scoreColor}"></div>
          </div>
          <span class="score-label" style="color:${scoreColor}">${score}/10</span>
        </div>
        <p class="trip-analysis-text">${analysisHtml}</p>
      </div>

      ${(strengths || weaknesses) ? `
      <div class="trip-analysis-card">
        <h4>Stärken &amp; Schwächen</h4>
        <div class="trip-analysis-swot">
          ${strengths  ? `<div><p class="swot-col-title strengths-title">Stärken</p><ul class="swot-list strengths-list">${strengths}</ul></div>`  : ''}
          ${weaknesses ? `<div><p class="swot-col-title weaknesses-title">Schwächen</p><ul class="swot-list weaknesses-list">${weaknesses}</ul></div>` : ''}
        </div>
      </div>
      ` : ''}

      ${suggestions ? `
      <div class="trip-analysis-card">
        <h4>Verbesserungsvorschläge</h4>
        <div class="suggestions-list">${suggestions}</div>
      </div>
      ` : ''}
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
            ${buildHeroPhotoLoading('sm')}
            <div class="further-activity-content">
              <strong>${esc(act.name)}</strong>
              <p>${esc(act.description)}</p>
              <div class="activity-meta">
                ${act.duration_hours}h
                ${act.price_chf > 0 ? ` · CHF ${act.price_chf}` : ' · kostenlos'}
                ${act.age_group ? ` · ${esc(act.age_group)}` : (act.suitable_for_children ? ' · familienfreundlich' : '')}
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
    drive:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 5v4h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
    activity: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
    meal:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>`,
    break:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>`,
    check_in: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
  };
  const pinIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;

  return `
    <div class="day-timeblocks">
      <div class="timeblocks-timeline">
        ${blocks.map(tb => `
          <div class="time-block type-${esc(tb.activity_type)}">
            <div class="time-block-time">${esc(tb.time)}</div>
            <div class="time-block-dot"></div>
            <div class="time-block-content">
              <div class="time-block-header">
                <span class="time-block-icon">${typeIcon[tb.activity_type] || pinIcon}</span>
                <strong>${esc(tb.title)}</strong>
                <span class="time-block-duration">${tb.duration_minutes} min</span>
              </div>
              ${tb.location ? `<div class="time-block-location">${pinIcon} ${esc(tb.location)}</div>` : ''}
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

  // Sidebar items
  const sidebarItems = stops.map((stop, i) => {
    const flag = FLAGS[stop.country] || '';
    return `
      <div class="stops-sidebar-item${i === 0 ? ' active' : ''}" data-target="guide-stop-${stop.id}">
        <span class="sidebar-stop-num">${stop.id}</span>
        <span class="sidebar-stop-label">${flag} ${esc(stop.region)}</span>
      </div>
    `;
  }).join('');

  // Stop cards
  const stopCards = stops.map((stop, i) => {
    const flag = FLAGS[stop.country] || '';
    const acc  = stop.accommodation || {};
    const acts = stop.top_activities || [];
    const rests = stop.restaurants || [];
    const further = stop.further_activities || [];
    const isFirst = i === 0;

    // Day plans that fall within this stop's nights
    const arrivalDay = stop.arrival_day || 1;
    const stopDays = dayPlans.filter(d =>
      d.day >= arrivalDay && d.day < arrivalDay + (stop.nights || 1)
    );

    const accHtml = acc.name ? (() => {
      const allOpts = stop.all_accommodation_options || [];
      const altOpts = allOpts.filter(o => o.name !== acc.name);
      return `
      <div class="stop-accommodation">
        <h4>Unterkunft</h4>
        ${buildHeroPhotoLoading('sm')}
        <div class="acc-summary">
          <strong>${esc(acc.name)}</strong>
          <span class="acc-selected-badge">Gewählt</span>
          ${acc.is_geheimtipp ? `<span class="geheimtipp-badge">Geheimtipp</span>` : ''}
          <span class="acc-type-tag">${esc(acc.type || '')}</span>
          <span class="acc-price-tag">ca. CHF ${(acc.total_price_chf || 0).toLocaleString('de-CH')}</span>
        </div>
        ${acc.description ? `<div class="acc-guide-description">${esc(acc.description)}</div>` : ''}
        <div class="acc-guide-links">
          ${acc.booking_url ? `<a href="${safeUrl(acc.booking_url)}" target="_blank" class="acc-booking-link">Bei Booking.com anschauen <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
          ${acc.booking_search_url ? `<a href="${safeUrl(acc.booking_search_url)}" target="_blank" class="acc-booking-link acc-booking-search">Bei Booking.com suchen <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
          ${acc.hotel_website_url ? `<a href="${safeUrl(acc.hotel_website_url)}" target="_blank" class="acc-website-link">Hotelwebseite <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
        </div>
        ${altOpts.length ? `
        <details class="acc-alt-options">
          <summary>Weitere Optionen (${altOpts.length})</summary>
          <div class="acc-alt-list">
            ${altOpts.map(o => `
              <div class="acc-alt-item">
                ${buildHeroPhotoLoading('sm')}
                <div class="acc-alt-summary">
                  <strong>${esc(o.name)}</strong>
                  ${o.is_geheimtipp ? `<span class="geheimtipp-badge">Geheimtipp</span>` : ''}
                  <span class="acc-type-tag">${esc(o.type || '')}</span>
                  <span class="acc-price-tag">ca. CHF ${(o.total_price_chf || 0).toLocaleString('de-CH')}</span>
                </div>
                <div class="acc-guide-links">
                  ${o.booking_url ? `<a href="${safeUrl(o.booking_url)}" target="_blank" class="acc-booking-link">Bei Booking.com <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
                  ${o.booking_search_url ? `<a href="${safeUrl(o.booking_search_url)}" target="_blank" class="acc-booking-link acc-booking-search">Booking.com suchen <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
                  ${o.hotel_website_url ? `<a href="${safeUrl(o.hotel_website_url)}" target="_blank" class="acc-website-link">Hotelwebseite <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12" aria-hidden="true" style="vertical-align:-1px;margin-left:3px"><polyline points="9 6 15 12 9 18"/></svg></a>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </details>
        ` : ''}
      </div>
      `;
    })() : '';

    const actsHtml = acts.length ? `
      <details class="stop-section-collapse" open>
        <summary class="stop-section-summary">Aktivitäten (${acts.length})</summary>
        <div class="stop-activities">
          <div class="activities-grid">
            ${acts.map(act => `
              <div class="activity-card">
                ${buildHeroPhotoLoading('sm')}
                <div class="activity-content">
                  <strong>${esc(act.name)}</strong>
                  <p>${esc(act.description)}</p>
                  <div class="activity-meta">
                    ${act.duration_hours}h
                    ${act.price_chf > 0 ? ` · CHF ${act.price_chf}` : ' · kostenlos'}
                    ${act.age_group ? ` · ${esc(act.age_group)}` : (act.suitable_for_children ? ' · familienfreundlich' : '')}
                  </div>
                  ${act.google_maps_url ? `<a href="${safeUrl(act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </details>
    ` : '';

    const restsHtml = rests.length ? `
      <details class="stop-section-collapse" open>
        <summary class="stop-section-summary">Restaurants (${rests.length})</summary>
        <div class="stop-restaurants">
          <div class="restaurants-list">
            ${rests.map(r => `
              <div class="restaurant-item">
                ${buildHeroPhotoLoading('sm')}
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
      </details>
    ` : '';

    const daysHtml = stopDays.length ? `
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
    ` : '';

    return `
      <div class="stop-card" id="guide-stop-${stop.id}" data-stop-id="${stop.id}">
        <button class="stop-header stop-toggle" aria-expanded="${isFirst}" data-stop-id="${stop.id}">
          <div class="stop-header-left">
            <div class="stop-number">Stop ${stop.id}</div>
            <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
            <div class="stop-meta">
              Tag ${stop.arrival_day} · ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
              ${stop.drive_hours_from_prev > 0 ? ` · ${stop.drive_hours_from_prev}h Fahrt` : ''}
              ${stop.drive_km_from_prev > 0 ? ` · ${stop.drive_km_from_prev} km` : ''}
            </div>
          </div>
          <div class="stop-header-right">
            <button class="replace-stop-btn" onclick="event.stopPropagation(); openReplaceStopModal(${stop.id}, ${stop.nights})" title="Stopp ersetzen">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
              Ersetzen
            </button>
            ${(stop.place_id || stop.google_maps_url) ? `<a href="${safeUrl(stop.place_id ? `https://www.google.com/maps/place/?q=place_id:${stop.place_id}` : stop.google_maps_url)}" target="_blank" class="maps-link" onclick="event.stopPropagation()">Maps</a>` : ''}
            <span class="stop-toggle-arrow">${isFirst
              ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg>`
              : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="9 6 15 12 9 18"/></svg>`}</span>
          </div>
        </button>

        <div class="stop-body"${isFirst ? '' : ' style="display:none"'}>
          ${buildHeroPhotoLoading('lg')}
          ${renderTravelGuide(stop.travel_guide)}
          ${accHtml}
          ${actsHtml}
          ${renderFurtherActivities(further)}
          ${restsHtml}
          ${daysHtml}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="stops-layout">
      <aside class="stops-sidebar">
        <div class="stops-sidebar-inner">
          ${sidebarItems}
        </div>
      </aside>
      <div class="stops-main">
        ${stopCards}
      </div>
    </div>
  `;
}

// One-time event delegation on #guide-content (set up in _initGuideDelegation)
let _guideDelegationReady = false;
let _stopsObserver = null;

function _initGuideDelegation() {
  if (_guideDelegationReady) return;
  _guideDelegationReady = true;
  const root = document.getElementById('guide-content');
  if (!root) return;

  root.addEventListener('click', (e) => {
    // Sidebar item click
    const sidebarItem = e.target.closest('.stops-sidebar-item');
    if (sidebarItem) {
      const targetId = sidebarItem.dataset.target;
      const stopId = targetId.replace('guide-stop-', '');
      document.querySelectorAll('.stops-sidebar-item').forEach(si => {
        si.classList.toggle('active', si === sidebarItem);
      });
      _expandOnlyStop(stopId);
      const el = document.getElementById(targetId);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    // Stop header toggle click
    const toggleBtn = e.target.closest('.stop-toggle');
    if (toggleBtn) {
      const stopId = toggleBtn.dataset.stopId;
      _toggleStop(stopId, true);
    }
  });
}

function _initStopsSidebar() {
  // Set up delegation (once)
  _initGuideDelegation();

  // IntersectionObserver to highlight active stop in sidebar
  if (_stopsObserver) _stopsObserver.disconnect();
  _stopsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const stopId = entry.target.dataset.stopId;
        document.querySelectorAll('.stops-sidebar-item').forEach(item => {
          item.classList.toggle('active', item.dataset.target === `guide-stop-${stopId}`);
        });
      }
    });
  }, { threshold: 0.15, rootMargin: '-80px 0px -60% 0px' });

  document.querySelectorAll('.stop-card').forEach(card => _stopsObserver.observe(card));
}

function _toggleStop(stopId, scrollIntoView) {
  const card = document.getElementById(`guide-stop-${stopId}`);
  if (!card) return;
  const body = card.querySelector('.stop-body');
  const btn  = card.querySelector('.stop-toggle');
  const arrow = btn?.querySelector('.stop-toggle-arrow');
  const isOpen = body.style.display !== 'none';

  body.style.display = isOpen ? 'none' : 'block';
  if (btn)   btn.setAttribute('aria-expanded', String(!isOpen));
  if (arrow) arrow.innerHTML = isOpen
    ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="9 6 15 12 9 18"/></svg>`
    : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg>`;
}

function _expandOnlyStop(stopId) {
  document.querySelectorAll('.stop-card').forEach(card => {
    const id = card.dataset.stopId;
    const body  = card.querySelector('.stop-body');
    const btn   = card.querySelector('.stop-toggle');
    const arrow = btn?.querySelector('.stop-toggle-arrow');
    const open  = String(id) === String(stopId);
    body.style.display = open ? 'block' : 'none';
    if (btn)   btn.setAttribute('aria-expanded', String(open));
    if (arrow) arrow.innerHTML = open
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12"><polyline points="9 6 15 12 9 18"/></svg>`;
  });
}

function renderCalendar(plan) {
  const stops = plan.stops || [];
  const dayPlans = plan.day_plans || [];

  const _ic = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">${d}</svg>`;
  const typeIcon = {
    drive:    _ic('<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 5v4h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>'),
    checkin:  _ic('<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'),
    activity: _ic('<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'),
    rest:     _ic('<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v1z"/>'),
    mixed:    _ic('<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>'),
  };
  const _pinIcon = _ic('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>');
  const typeLabel = { drive: 'Fahrt', checkin: 'Ankunft', activity: 'Erlebnis', rest: 'Entspannen', mixed: 'Gemischt' };

  // Build a cell per day_plan entry
  const cells = dayPlans.map(dp => {
    // Determine type based on day plan type field
    const raw = (dp.type || 'mixed').toLowerCase();
    const type = raw === 'drive' ? 'drive'
               : raw === 'rest'  ? 'rest'
               : raw === 'activity' ? 'activity'
               : raw === 'mixed'   ? 'mixed'
               : 'mixed';

    // Find which stop this day belongs to
    const stop = stops.find(s => {
      const arr = s.arrival_day || 1;
      return dp.day >= arr && dp.day < arr + (s.nights || 1);
    });
    const flag = stop ? (FLAGS[stop.country] || '') : '';
    const stopName = stop ? stop.region : '';
    const stopId = stop ? stop.id : null;

    return `
      <div class="cal-day-cell" data-type="${esc(type)}" data-stop-id="${stopId || ''}"
           title="${esc(dp.title)}" tabindex="0" role="button">
        <div class="cal-day-num">${dp.day}</div>
        <div class="cal-day-icon">${typeIcon[type] || _pinIcon}</div>
        <div class="cal-day-label">${esc(dp.title || typeLabel[type])}</div>
        ${stopName ? `<div class="cal-day-stop">${flag} ${esc(stopName)}</div>` : ''}
        ${dp.date ? `<div class="cal-day-date">${esc(dp.date)}</div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <div class="calendar-section">
      <h3 class="calendar-title">Reise-Kalender</h3>
      <p class="calendar-hint">Klick auf einen Tag öffnet den Stop im Reiseführer.</p>
      <div class="calendar-scroll-wrap">
        <div class="calendar-timeline">
          ${cells}
        </div>
      </div>
      <div class="calendar-legend">
        ${Object.entries(typeIcon).map(([t, icon]) =>
          `<span class="cal-legend-item" data-type="${t}">${icon} ${typeLabel[t]}</span>`
        ).join('')}
      </div>
    </div>
  `;
}

function _initCalendarClicks(plan) {
  document.querySelectorAll('.cal-day-cell[data-stop-id]').forEach(cell => {
    const stopId = cell.dataset.stopId;
    if (!stopId) return;
    cell.addEventListener('click', () => {
      switchGuideTab('stops');
      requestAnimationFrame(() => {
        _expandOnlyStop(stopId);
        document.getElementById(`guide-stop-${stopId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
    cell.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); cell.click(); }
    });
  });
}

function _scrollToGuideStop(stopId) {
  switchGuideTab('stops');
  // After tab switch the DOM is re-rendered; use rAF to wait one frame
  requestAnimationFrame(() => {
    _expandOnlyStop(stopId);
    document.getElementById(`guide-stop-${stopId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function _initGuideMap(plan) {
  if (typeof GoogleMaps === 'undefined' || !window.google) {
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: 'Reiseführer-Karte nicht geladen — Google Maps API nicht verfügbar' });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
    return;
  }

  const stops = plan.stops || [];

  // initGuideMap always creates a fresh instance (element replaced by innerHTML)
  const map = GoogleMaps.initGuideMap('guide-map', { center: { lat: 47, lng: 8 }, zoom: 6 });
  if (!map) return;

  _guideMarkers = [];
  _guidePolyline = null;

  const bounds = new google.maps.LatLngBounds();
  let hasBounds = false;
  const routePoints = [];

  // Start pin (green S)
  if (plan.start_lat && plan.start_lng) {
    const pos = { lat: plan.start_lat, lng: plan.start_lng };
    const infoWin = new google.maps.InfoWindow({ content: `<b>Start: ${esc(plan.start_location)}</b>` });
    const m = GoogleMaps.createDivMarker(map, pos,
      `<div class="map-marker-anchor start-pin">S</div>`,
      () => infoWin.open({ map, position: pos })
    );
    _guideMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
    routePoints.push(new google.maps.LatLng(pos.lat, pos.lng));
  }

  stops.forEach((stop, i) => {
    const sLat = stop.lat;
    const sLng = stop.lng;
    if (!sLat || !sLng) return;

    const isLast = i === stops.length - 1;
    const pos = { lat: sLat, lng: sLng };
    const infoContent = `<b>${FLAGS[stop.country] || ''} ${esc(stop.region)}</b><br>${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}`;
    const infoWin = new google.maps.InfoWindow({ content: infoContent });
    const markerHtml = isLast
      ? `<div class="map-marker-anchor target-pin">Z</div>`
      : `<div class="map-marker-num">${stop.id}</div>`;
    const stopId = stop.id;
    const m = (stop.place_id
      ? GoogleMaps.createPlaceMarker(map, stop.place_id, pos, markerHtml, () => { infoWin.open({ map, position: pos }); _scrollToGuideStop(stopId); })
      : GoogleMaps.createDivMarker(map, pos, markerHtml, () => { infoWin.open({ map, position: pos }); _scrollToGuideStop(stopId); }));
    _guideMarkers.push(m);
    bounds.extend(pos);
    hasBounds = true;
    routePoints.push(new google.maps.LatLng(sLat, sLng));
  });

  // Solid polyline through all route points
  if (routePoints.length >= 2) {
    _guidePolyline = new google.maps.Polyline({
      map,
      path: routePoints,
      strokeColor: '#0EA5E9',
      strokeOpacity: 0.8,
      strokeWeight: 3,
    });
  }

  if (hasBounds) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
      if (map.getZoom() > 9) map.setZoom(9);
    });
  }
}

/**
 * Lazily load images for an entity (stop, activity, restaurant, accommodation)
 * via Google Places and fill the hero-photo skeleton container.
 */
async function _lazyLoadEntityImages(containerEl, placeName, lat, lng, context, sizeClass) {
  if (!containerEl || typeof GoogleMaps === 'undefined') return;
  try {
    const urls = await GoogleMaps.getPlaceImages(placeName, lat, lng, context);
    const placeholder = containerEl.querySelector('.hero-photo-loading');
    const size = sizeClass || (placeholder?.classList.contains('hero-photo--lg') ? 'lg'
      : placeholder?.classList.contains('hero-photo--sm') ? 'sm' : 'md');
    const newHtml = buildHeroPhoto(urls, placeName, size);
    if (!newHtml) return;
    if (placeholder) {
      const tmp = document.createElement('div');
      tmp.innerHTML = newHtml;
      placeholder.replaceWith(tmp.firstElementChild);
    } else {
      const tmp = document.createElement('div');
      tmp.innerHTML = newHtml;
      containerEl.insertBefore(tmp.firstElementChild, containerEl.firstChild);
    }
  } catch (e) {
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: `_lazyLoadEntityImages fehlgeschlagen für «${placeName}»: ${e.message}` });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
  }
}

/** Walk the rendered stops section and lazy-load images for all entities. */
function _lazyLoadStopImages(plan) {
  const stops = plan.stops || [];
  stops.forEach(stop => {
    const stopEl = document.getElementById(`guide-stop-${stop.id}`);
    if (!stopEl) return;
    const lat = stop.lat;
    const lng = stop.lng;

    // Stop overview images
    _lazyLoadEntityImages(stopEl.querySelector('.stop-header')?.parentElement || stopEl, stop.region, lat, lng, 'city');

    // Accommodation
    const accEl = stopEl.querySelector('.stop-accommodation');
    if (accEl && stop.accommodation) {
      _lazyLoadEntityImages(accEl, stop.accommodation.name, lat, lng, 'hotel');
      // Alt options
      accEl.querySelectorAll('.acc-alt-item').forEach((el, i) => {
        const altOpts = (stop.all_accommodation_options || []).filter(o => o.name !== stop.accommodation.name);
        const o = altOpts[i];
        if (o) _lazyLoadEntityImages(el, o.name, lat, lng, 'hotel');
      });
    }

    // Top activities
    stopEl.querySelectorAll('.activity-card').forEach((el, i) => {
      const act = (stop.top_activities || [])[i];
      if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
    });

    // Further activities
    stopEl.querySelectorAll('.further-activity-item').forEach((el, i) => {
      const act = (stop.further_activities || [])[i];
      if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
    });

    // Restaurants
    stopEl.querySelectorAll('.restaurant-item').forEach((el, i) => {
      const rest = (stop.restaurants || [])[i];
      if (rest) _lazyLoadEntityImages(el, rest.name, lat, lng, 'restaurant');
    });
  });
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
    { label: 'Unterkunft',  value: acc,   color: '#0EA5E9' },
    { label: 'Aktivitäten', value: act,   color: '#22C55E' },
    { label: 'Verpflegung', value: food,  color: '#F59E0B' },
    { label: 'Treibstoff',  value: fuel,  color: '#EF4444' },
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

  const savedId = plan._saved_travel_id || null;
  const btn = document.getElementById('replan-current-btn');

  if (!savedId) {
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = 'Zuerst in «Meine Reisen» speichern';
      setTimeout(() => { btn.textContent = orig; }, 3000);
    }
    return;
  }

  // Inline two-click confirmation
  if (btn && btn.dataset.confirmPending !== '1') {
    btn.dataset.confirmPending = '1';
    btn.textContent = 'Bestätigen?';
    btn.classList.add('btn-warning');
    setTimeout(() => {
      if (btn && btn.dataset.confirmPending === '1') {
        btn.dataset.confirmPending = '';
        btn.textContent = 'Neu berechnen';
        btn.classList.remove('btn-warning');
      }
    }, 3000);
    return;
  }

  if (btn) {
    btn.dataset.confirmPending = '';
    btn.disabled = true;
    btn.textContent = 'Wird gestartet…';
    btn.classList.remove('btn-warning');
  }

  try {
    const { job_id } = await apiReplanTravel(savedId);
    S.jobId = job_id;
    showSection('progress');
    Router.navigate('/progress/' + job_id);
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
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Fehler — nochmals versuchen';
      setTimeout(() => { if (btn) btn.textContent = 'Neu berechnen'; }, 4000);
    }
    console.error('Replan-Fehler:', err);
  }
}


// ---------------------------------------------------------------------------
// Replace Stop — Modal + SSE handling
// ---------------------------------------------------------------------------

let _replaceStopSSE = null;

function openReplaceStopModal(stopId, currentNights) {
  const plan = S.result;
  if (!plan) return;

  const savedId = plan._saved_travel_id;
  if (!savedId) {
    alert('Reise muss zuerst gespeichert werden.');
    return;
  }

  const stop = (plan.stops || []).find(s => s.id === stopId);
  if (!stop) return;

  const stopIdx = (plan.stops || []).indexOf(stop);
  const prevLabel = stopIdx > 0
    ? plan.stops[stopIdx - 1].region
    : plan.start_location || '';
  const nextLabel = stopIdx < plan.stops.length - 1
    ? plan.stops[stopIdx + 1].region
    : '';

  // Remove existing modal
  const existing = document.getElementById('replace-stop-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'replace-stop-modal';
  modal.className = 'replace-modal';
  modal.innerHTML = `
    <div class="replace-modal-backdrop" onclick="closeReplaceStopModal()"></div>
    <div class="replace-modal-content">
      <div class="replace-modal-header">
        <h3>Stopp ersetzen: ${esc(stop.region)}</h3>
        <button class="replace-modal-close" onclick="closeReplaceStopModal()">&times;</button>
      </div>

      <div class="replace-modal-tabs">
        <button class="replace-tab active" data-tab="manual" onclick="_switchReplaceTab('manual')">Ort eingeben</button>
        <button class="replace-tab" data-tab="search" onclick="_switchReplaceTab('search')">Neue Suche</button>
      </div>

      <div class="replace-tab-content" id="replace-tab-manual">
        <div class="replace-form">
          <label>Neuer Ort</label>
          <input type="text" id="replace-manual-location" class="replace-input" placeholder="z.B. Lyon, Frankreich" />
          <label>Nächte <small>(Standard: ${currentNights})</small></label>
          <input type="number" id="replace-manual-nights" class="replace-input" min="1" max="14" value="${currentNights}" />
          <button class="btn btn-primary replace-submit-btn" id="replace-manual-btn"
            onclick="_doManualReplace(${savedId}, ${stopId})">Ersetzen</button>
        </div>
      </div>

      <div class="replace-tab-content" id="replace-tab-search" style="display:none">
        <p class="replace-search-info">
          Suche basierend auf ${esc(prevLabel)} → ${nextLabel ? esc(nextLabel) : 'Reiseende'}
          mit den Original-Einstellungen.
        </p>
        <button class="btn btn-primary replace-submit-btn" id="replace-search-btn"
          onclick="_doSearchReplace(${savedId}, ${stopId})">Alternativen suchen</button>
        <div id="replace-search-results" class="replace-search-results"></div>
      </div>

      <div id="replace-progress" class="replace-progress" style="display:none">
        <div class="replace-spinner"></div>
        <p id="replace-progress-msg">Wird bearbeitet…</p>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add('visible'));

  // Focus input
  const input = document.getElementById('replace-manual-location');
  if (input) setTimeout(() => input.focus(), 100);
}

function closeReplaceStopModal() {
  const modal = document.getElementById('replace-stop-modal');
  if (modal) {
    modal.classList.remove('visible');
    setTimeout(() => modal.remove(), 200);
  }
  if (_replaceStopSSE) {
    _replaceStopSSE.close();
    _replaceStopSSE = null;
  }
}

function _switchReplaceTab(tab) {
  document.querySelectorAll('.replace-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById('replace-tab-manual').style.display = tab === 'manual' ? '' : 'none';
  document.getElementById('replace-tab-search').style.display = tab === 'search' ? '' : 'none';
}

function _showReplaceProgress(msg) {
  const p = document.getElementById('replace-progress');
  const m = document.getElementById('replace-progress-msg');
  if (p) p.style.display = '';
  if (m) m.textContent = msg || 'Wird bearbeitet…';
}

function _hideReplaceProgress() {
  const p = document.getElementById('replace-progress');
  if (p) p.style.display = 'none';
}

async function _doManualReplace(travelId, stopId) {
  const loc = (document.getElementById('replace-manual-location')?.value || '').trim();
  const nights = parseInt(document.getElementById('replace-manual-nights')?.value) || 1;
  if (!loc) { alert('Bitte einen Ort eingeben.'); return; }

  const btn = document.getElementById('replace-manual-btn');
  if (btn) btn.disabled = true;
  _showReplaceProgress('Ort wird gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'manual', loc, nights);
    _listenForReplaceComplete(res.job_id, travelId);
  } catch (err) {
    _hideReplaceProgress();
    if (btn) btn.disabled = false;
    alert('Fehler: ' + err.message);
  }
}

async function _doSearchReplace(travelId, stopId) {
  const btn = document.getElementById('replace-search-btn');
  if (btn) btn.disabled = true;
  _showReplaceProgress('Alternativen werden gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'search');
    _hideReplaceProgress();
    if (btn) btn.disabled = false;

    const options = res.options || [];
    const container = document.getElementById('replace-search-results');
    if (!container) return;

    if (!options.length) {
      container.innerHTML = '<p class="replace-no-results">Keine Alternativen gefunden.</p>';
      return;
    }

    container.innerHTML = options.map((opt, i) => `
      <div class="replace-option-card" onclick="_selectSearchOption(${travelId}, '${esc(res.job_id)}', ${i})">
        <div class="replace-option-header">
          <strong>${FLAGS[opt.country] || ''} ${esc(opt.region)}</strong>
          <span class="replace-option-type">${esc(opt.option_type || '')}</span>
        </div>
        <p class="replace-option-teaser">${esc(opt.teaser || '')}</p>
        <div class="replace-option-meta">
          ${opt.drive_hours ? `${opt.drive_hours}h Fahrt` : ''}
          ${opt.drive_km ? ` · ${opt.drive_km} km` : ''}
          ${opt.nights ? ` · ${opt.nights} Nacht${opt.nights !== 1 ? 'e' : ''}` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    _hideReplaceProgress();
    if (btn) btn.disabled = false;
    alert('Fehler: ' + err.message);
  }
}

async function _selectSearchOption(travelId, jobId, optionIndex) {
  _showReplaceProgress('Gewählter Stopp wird recherchiert…');

  try {
    const res = await apiReplaceStopSelect(travelId, jobId, optionIndex);
    _listenForReplaceComplete(res.job_id, travelId);
  } catch (err) {
    _hideReplaceProgress();
    alert('Fehler: ' + err.message);
  }
}

function _listenForReplaceComplete(jobId, travelId) {
  _showReplaceProgress('Recherche läuft…');

  _replaceStopSSE = openSSE(jobId, {
    replace_stop_progress: (data) => {
      const msg = data.message || 'Wird bearbeitet…';
      _showReplaceProgress(msg);
    },
    replace_stop_complete: (data) => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      // data is the full updated plan
      data._saved_travel_id = travelId;
      S.result = data;
      lsSet(LS_RESULT, { jobId: data.job_id || jobId, savedAt: new Date().toISOString(), plan: data });
      closeReplaceStopModal();
      renderGuide(data, activeTab);
    },
    job_error: (data) => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      _hideReplaceProgress();
      alert('Fehler beim Ersetzen: ' + (data.error || 'Unbekannter Fehler'));
    },
    debug_log: (data) => {
      if (data.message) _showReplaceProgress(data.message);
    },
  });
}
