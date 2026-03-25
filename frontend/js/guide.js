'use strict';

let activeTab = 'overview';
let _guideMarkers = [];
let _guidePolyline = null;
let _initializedStopMaps = new Set();
let _activeStopId = null;
let _activeDayNum = null;
let _editInProgress = false;
let _editSSE = null;
let _dragStopSourceIndex = null;

// Persistent map + bidirectional sync state
let _scrollDebounce = null;
let _lastPannedStopId = null;
let _userInteractingWithMap = false;
let _userInteractionTimeout = null;
let _cardObserver = null;
let _guideMapInitialized = false;

function showTravelGuide(plan) {
  S.result = plan;
  if (typeof updateSidebar === 'function') updateSidebar();
  _setupGuideMap(plan);
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
      break;
    case 'stops':
      _initializedStopMaps = new Set();
      if (_activeStopId !== null) {
        content.innerHTML = renderStopDetail(plan, _activeStopId);
        requestAnimationFrame(() => {
          _initGuideDelegation();
          const stop = (plan.stops || []).find(s => String(s.id) === String(_activeStopId));
          if (stop) {
            _initStopMap(stop);
            _lazyLoadSingleStopImages(plan, stop);
          }
        });
      } else {
        content.innerHTML = renderStopsOverview(plan);
        requestAnimationFrame(() => {
          _initGuideDelegation();
          _lazyLoadOverviewImages(plan);
          _initScrollSync();
        });
      }
      break;
    case 'calendar':
      content.innerHTML = renderCalendar(plan);
      _initCalendarClicks(plan);
      break;
    case 'days':
      if (_activeDayNum !== null) {
        content.innerHTML = renderDayDetail(plan, _activeDayNum);
        requestAnimationFrame(() => {
          _initGuideDelegation();
          _initDayDetailMap(plan, _activeDayNum);
        });
      } else {
        content.innerHTML = renderDaysOverview(plan);
        requestAnimationFrame(() => _initGuideDelegation());
      }
      break;
    case 'budget':     content.innerHTML = renderBudget(plan);    break;
    default:
      content.innerHTML = renderOverview(plan);
  }

  // Update persistent map for current tab
  _updateMapForTab(plan, activeTab);

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
  if (tab !== 'stops') _activeStopId = null;
  if (tab !== 'days') _activeDayNum = null;
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

      ${(plan.day_plans && plan.day_plans.length) ? `
      <div class="overview-dayplan-cta" onclick="switchGuideTab('days')">
        <div class="overview-dayplan-cta-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        </div>
        <div class="overview-dayplan-cta-text">
          <strong>Tagesplan</strong>
          <span>${plan.day_plans.length} Tage mit stündlichen Zeitblöcken, Karte und Aktivitäten</span>
        </div>
        <svg class="overview-dayplan-cta-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="20" height="20"><polyline points="9 6 15 12 9 18"/></svg>
      </div>
      ` : ''}

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
              ${(act.place_id || act.google_maps_url) ? `<a href="${safeUrl(act.place_id ? `https://www.google.com/maps/place/?q=place_id:${act.place_id}` : act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
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
                ${(tb.place_id || tb.google_maps_url) ? `<a href="${safeUrl(tb.place_id ? `https://www.google.com/maps/place/?q=place_id:${tb.place_id}` : tb.google_maps_url)}" target="_blank" class="tb-link maps-link">Maps</a>` : ''}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Extracted stop-section HTML helpers
// ---------------------------------------------------------------------------

function _renderAccommodationHtml(stop) {
  const acc = stop.accommodation || {};
  if (!acc.name) return '';
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
              <div class="acc-alt-badges">
                ${o.is_geheimtipp ? `<span class="geheimtipp-badge">Geheimtipp</span>` : ''}
                <span class="acc-type-tag">${esc(o.type || '')}</span>
                <span class="acc-price-tag">ca. CHF ${(o.total_price_chf || 0).toLocaleString('de-CH')}</span>
              </div>
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
}

function _renderActivitiesHtml(stop) {
  const acts = stop.top_activities || [];
  if (!acts.length) return '';
  return `
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
                ${(act.place_id || act.google_maps_url) ? `<a href="${safeUrl(act.place_id ? `https://www.google.com/maps/place/?q=place_id:${act.place_id}` : act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </details>
  `;
}

function _renderRestaurantsHtml(stop) {
  const rests = stop.restaurants || [];
  if (!rests.length) return '';
  return `
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
  `;
}

function _renderDayExamplesHtml(stop, dayPlans) {
  const arrivalDay = stop.arrival_day || 1;
  const stopDays = dayPlans.filter(d =>
    d.day >= arrivalDay && d.day < arrivalDay + (stop.nights || 1)
  );
  if (!stopDays.length) return '';

  const typeLabel = { drive: 'Fahrt', rest: 'Entspannen', activity: 'Erlebnis', mixed: 'Gemischt' };
  const typeColor = { drive: 'var(--accent)', rest: '#7C6BE0', activity: '#E8A84C', mixed: '#5AB8A0' };

  return `
    <div class="stop-day-examples">
      <h4>Tagespläne</h4>
      <div class="stop-day-cta-list">
        ${stopDays.map(dp => {
          const type = (dp.type || 'mixed').toLowerCase();
          const blockCount = (dp.time_blocks || []).length;
          return `
          <div class="stop-day-cta" data-day-num="${dp.day}" style="border-left-color: ${typeColor[type] || typeColor.mixed}">
            <div class="stop-day-cta-left">
              <span class="stop-day-cta-num">Tag ${dp.day}</span>
              ${dp.date ? `<span class="stop-day-cta-date">${esc(dp.date)}</span>` : ''}
              <span class="day-type-badge type-${esc(type)}">${typeLabel[type] || esc(dp.type)}</span>
            </div>
            <div class="stop-day-cta-center">
              <strong>${esc(dp.title)}</strong>
              <span>${blockCount} Zeitblöcke</span>
            </div>
            <svg class="stop-day-cta-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="18" height="18"><polyline points="9 6 15 12 9 18"/></svg>
          </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Day Plan helpers
// ---------------------------------------------------------------------------

function _findStopsForDay(plan, dayNum) {
  const stops = plan.stops || [];
  return stops.filter(s => {
    const arr = s.arrival_day || 1;
    return dayNum >= arr && dayNum < arr + (s.nights || 1);
  });
}

function renderDaysOverview(plan) {
  const dayPlans = plan.day_plans || [];
  const stops = plan.stops || [];
  const typeLabel = { drive: 'Fahrt', rest: 'Entspannen', activity: 'Erlebnis', mixed: 'Gemischt' };
  const typeColor = { drive: 'var(--accent)', rest: '#7C6BE0', activity: '#E8A84C', mixed: '#5AB8A0' };

  const cards = dayPlans.map(dp => {
    const type = (dp.type || 'mixed').toLowerCase();
    const dayStops = _findStopsForDay(plan, dp.day);
    const stopInfo = dayStops.map(s => `${FLAGS[s.country] || ''} ${esc(s.region)}`).join(', ');
    const desc = (dp.description || '').length > 120 ? dp.description.substring(0, 120) + '…' : (dp.description || '');

    return `
      <div class="day-overview-card" data-day-num="${dp.day}" style="border-left-color: ${typeColor[type] || typeColor.mixed}">
        <div class="day-overview-card-body">
          <div class="day-overview-top">
            <span class="day-overview-num">Tag ${dp.day}</span>
            ${dp.date ? `<span class="day-overview-date">${esc(dp.date)}</span>` : ''}
            <span class="day-type-badge type-${esc(type)}">${typeLabel[type] || esc(dp.type)}</span>
          </div>
          <h3>${esc(dp.title)}</h3>
          <p class="day-overview-desc">${esc(desc)}</p>
          ${stopInfo ? `<div class="day-overview-stop">${stopInfo}</div>` : ''}
          ${dp.stops_on_route.length ? `<div class="day-overview-route">${dp.stops_on_route.map(s => `<span class="day-route-tag">${esc(s)}</span>`).join(' → ')}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="days-overview-grid">
      ${cards}
    </div>
  `;
}

function renderDayDetail(plan, dayNum) {
  const dayPlans = plan.day_plans || [];
  const stops = plan.stops || [];
  const idx = dayPlans.findIndex(dp => dp.day === dayNum);
  const dp = dayPlans[idx];
  if (!dp) return renderDaysOverview(plan);

  const type = (dp.type || 'mixed').toLowerCase();
  const typeLabel = { drive: 'Fahrt', rest: 'Entspannen', activity: 'Erlebnis', mixed: 'Gemischt' };
  const prev = idx > 0 ? dayPlans[idx - 1] : null;
  const next = idx < dayPlans.length - 1 ? dayPlans[idx + 1] : null;
  const dayStops = _findStopsForDay(plan, dayNum);

  // Sidebar
  const sidebarItems = dayPlans.map(d => `
    <div class="days-sidebar-item${d.day === dayNum ? ' active' : ''}" data-day-num="${d.day}">
      <span class="sidebar-day-num">${d.day}</span>
      <span class="sidebar-day-label">${esc((d.title || '').substring(0, 30))}</span>
    </div>
  `).join('');

  // POIs from matching stops
  let poisHtml = '';
  if (dayStops.length) {
    const acts = dayStops.flatMap(s => s.top_activities || []);
    const rests = dayStops.flatMap(s => s.restaurants || []);
    if (acts.length || rests.length) {
      poisHtml = `
        <div class="day-pois">
          <h4>Aktivitäten &amp; Restaurants am Stopp</h4>
          ${acts.length ? `<div class="activities-grid">${acts.map(act => `
            <div class="activity-card">
              <div class="activity-content">
                <strong>${esc(act.name)}</strong>
                <p>${esc(act.description)}</p>
                <div class="activity-meta">
                  ${act.duration_hours}h
                  ${act.price_chf > 0 ? ` · CHF ${act.price_chf}` : ' · kostenlos'}
                </div>
                ${(act.place_id || act.google_maps_url) ? `<a href="${safeUrl(act.place_id ? 'https://www.google.com/maps/place/?q=place_id:' + act.place_id : act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
              </div>
            </div>
          `).join('')}</div>` : ''}
          ${rests.length ? `<div class="restaurants-list">${rests.map(r => `
            <div class="restaurant-item">
              <div style="padding: 10px">
                <strong>${esc(r.name)}</strong>
                <span class="cuisine-tag">${esc(r.cuisine)}</span>
                <span class="price-range">${esc(r.price_range)}</span>
                ${r.family_friendly ? '<span class="family-tag">Familienfreundlich</span>' : ''}
              </div>
            </div>
          `).join('')}</div>` : ''}
        </div>
      `;
    }
  }

  return `
    <div class="days-layout">
      <aside class="days-sidebar">
        <div class="days-sidebar-inner">
          ${sidebarItems}
        </div>
      </aside>
      <div class="days-main">
        <div class="day-detail-nav">
          <button class="day-detail-back">\u2190 Alle Tage</button>
          <span class="day-detail-breadcrumb">Tag ${dp.day}: ${esc(dp.title)}</span>
        </div>

        <div class="day-detail-card">
          <div class="day-detail-header">
            <div class="day-detail-header-left">
              <span class="day-overview-num">Tag ${dp.day}</span>
              ${dp.date ? `<span class="day-overview-date">${esc(dp.date)}</span>` : ''}
              <span class="day-type-badge type-${esc(type)}">${typeLabel[type] || esc(dp.type)}</span>
            </div>
            <h3>${esc(dp.title)}</h3>
            <p>${esc(dp.description)}</p>
            ${dp.stops_on_route.length ? `<div class="day-overview-route">${dp.stops_on_route.map(s => `<span class="day-route-tag">${esc(s)}</span>`).join(' → ')}</div>` : ''}
            ${dp.google_maps_route_url ? `<a href="${safeUrl(dp.google_maps_route_url)}" target="_blank" class="btn btn-secondary btn-sm" style="margin-top:8px">Route in Google Maps</a>` : ''}
          </div>

          <div class="day-detail-map" id="day-map-${dayNum}"></div>

          ${renderDayTimeBlocks(dp)}

          ${poisHtml}
        </div>

        <div class="day-detail-prevnext">
          ${prev ? `<button class="btn btn-secondary day-nav-prev" data-day-num="${prev.day}">\u2190 Tag ${prev.day}</button>` : '<span></span>'}
          ${next ? `<button class="btn btn-secondary day-nav-next" data-day-num="${next.day}">Tag ${next.day} \u2192</button>` : '<span></span>'}
        </div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Day navigation helpers
// ---------------------------------------------------------------------------

function navigateToDay(dayNum) {
  _activeDayNum = Number(dayNum);
  const plan = S.result;
  if (!plan) return;
  renderGuide(plan, 'days');
  if (plan._saved_travel_id) {
    const title = plan.custom_name || plan.title || '';
    const base = Router.travelPath(plan._saved_travel_id, title);
    Router.navigate(base + '/days/' + dayNum, { skipDispatch: true });
  }
}

function navigateToDaysOverview() {
  _activeDayNum = null;
  const plan = S.result;
  if (!plan) return;
  renderGuide(plan, 'days');
  if (plan._saved_travel_id) {
    const title = plan.custom_name || plan.title || '';
    const base = Router.travelPath(plan._saved_travel_id, title);
    Router.navigate(base + '/days', { skipDispatch: true });
  }
}

function activateDayDetail(dayNum) {
  _activeDayNum = Number(dayNum);
  renderGuide(S.result, 'days');
}

// ---------------------------------------------------------------------------
// Day Detail Map
// ---------------------------------------------------------------------------

async function _initDayDetailMap(plan, dayNum) {
  if (!window.google || !google.maps) return;

  const elId = 'day-map-' + dayNum;
  const el = document.getElementById(elId);
  if (!el) return;

  const dayPlans = plan.day_plans || [];
  const dp = dayPlans.find(d => d.day === dayNum);
  if (!dp) return;

  const dayStops = _findStopsForDay(plan, dayNum);
  const refStop = dayStops[0];
  const centerLat = refStop?.lat || 47;
  const centerLng = refStop?.lng || 8;

  const map = GoogleMaps.initStopOverviewMap(elId, { center: { lat: centerLat, lng: centerLng }, zoom: 13 });
  if (!map) return;

  const entities = [];
  const timeBlocks = dp.time_blocks || [];

  // Time block entities (skip drive/break — they never resolve to useful locations)
  timeBlocks.forEach((tb, i) => {
    if (tb.activity_type === 'drive' || tb.activity_type === 'break') return;
    if (!tb.location && !tb.place_id) return;
    entities.push({
      key: `tb-${dayNum}-${i}`,
      placeId: tb.place_id || null,
      name: tb.location || tb.title,
      stopLat: centerLat, stopLng: centerLng,
      searchType: tb.activity_type === 'meal' ? 'restaurant'
                : tb.activity_type === 'check_in' ? 'hotel' : 'activity',
      type: 'timeblock', data: tb, index: i,
    });
  });

  // Activities from matching stops
  dayStops.forEach(stop => {
    (stop.top_activities || []).forEach((act, i) => {
      if (!act.name) return;
      entities.push({
        key: `day-act-${stop.id}-${i}`,
        placeId: act.place_id || null,
        lat: act.lat || null,
        lng: act.lon || null,
        name: act.name,
        stopLat: stop.lat, stopLng: stop.lng,
        searchType: 'activity',
        type: 'activity', data: act, index: i,
      });
    });
    (stop.restaurants || []).forEach((r, i) => {
      if (!r.name) return;
      entities.push({
        key: `day-rest-${stop.id}-${i}`,
        placeId: r.place_id || null,
        name: r.name,
        stopLat: stop.lat, stopLng: stop.lng,
        searchType: 'restaurant',
        type: 'restaurant', data: r, index: i,
      });
    });
    // Accommodation marker
    const acc = stop.accommodation;
    if (acc && acc.name) {
      entities.push({
        key: `day-hotel-${stop.id}`,
        placeId: acc.place_id || null,
        name: acc.name,
        stopLat: stop.lat, stopLng: stop.lng,
        searchType: 'hotel',
        type: 'hotel', data: acc, index: 0,
      });
    }
  });

  if (entities.length === 0) return;

  let coords;
  try {
    coords = await GoogleMaps.resolveEntityCoordinates(entities);
  } catch (e) {
    console.error('Day map coord resolve:', e);
    return;
  }

  if (coords.size === 0) return;

  const bounds = new google.maps.LatLngBounds();
  const routePoints = [];
  let _openInfoWindow = null;

  function attachHover(overlay, infoWindow, pos) {
    let hoverTimeout = null;
    const origOnAdd = overlay.onAdd;
    overlay.onAdd = function () {
      origOnAdd.call(this);
      const div = this._div;
      if (!div) return;
      div.addEventListener('mouseenter', () => {
        clearTimeout(hoverTimeout);
        if (_openInfoWindow) _openInfoWindow.close();
        infoWindow.setPosition(pos);
        infoWindow.open(map);
        _openInfoWindow = infoWindow;
      });
      div.addEventListener('mouseleave', () => {
        hoverTimeout = setTimeout(() => {
          infoWindow.close();
          if (_openInfoWindow === infoWindow) _openInfoWindow = null;
        }, 150);
      });
    };
  }

  // Build route anchors from stop coordinates
  // Start anchor: previous stop or plan start location
  const prevStop = plan.stops.find(s => {
    const arr = s.arrival_day || 1;
    return dayNum === arr && s.drive_hours_from_prev > 0;
  });
  if (prevStop) {
    // This is an arrival day — add departure point
    const stopIdx = plan.stops.indexOf(prevStop);
    const departure = stopIdx > 0 ? plan.stops[stopIdx - 1] : null;
    if (departure && departure.lat && departure.lng) {
      routePoints.push({ lat: departure.lat, lng: departure.lng });
    } else if (plan.start_lat && plan.start_lng) {
      routePoints.push({ lat: plan.start_lat, lng: plan.start_lng });
    }
  }

  // Time block numbered markers + collect route points
  let tbIndex = 0;
  timeBlocks.forEach((tb, i) => {
    if (tb.activity_type === 'drive' || tb.activity_type === 'break') return;
    const pos = coords.get(`tb-${dayNum}-${i}`);
    if (!pos) return;
    bounds.extend(pos);
    routePoints.push({ lat: pos.lat, lng: pos.lng });
    tbIndex++;

    const pinHtml = `<div class="stop-map-pin pin-timeblock">${tbIndex}</div>`;
    const popupHtml = `<div class="stop-map-popup"><strong>${esc(tb.time)} — ${esc(tb.title)}</strong>${tb.description ? `<p>${esc(tb.description)}</p>` : ''}</div>`;
    const infoWindow = new google.maps.InfoWindow({ content: popupHtml });
    const overlay = GoogleMaps.createDivMarker(map, pos, pinHtml, () => {
      if (_openInfoWindow) _openInfoWindow.close();
      infoWindow.setPosition(pos);
      infoWindow.open(map);
      _openInfoWindow = infoWindow;
    });
    attachHover(overlay, infoWindow, pos);
  });

  // End anchor: current stop coordinates
  if (refStop && refStop.lat && refStop.lng) {
    const lastRp = routePoints[routePoints.length - 1];
    // Only add if different from last route point
    if (!lastRp || Math.abs(lastRp.lat - refStop.lat) > 0.001 || Math.abs(lastRp.lng - refStop.lng) > 0.001) {
      routePoints.push({ lat: refStop.lat, lng: refStop.lng });
    }
  }

  // POI markers (activities, restaurants, hotel)
  for (const ent of entities) {
    if (ent.type === 'timeblock') continue;
    const pos = coords.get(ent.key);
    if (!pos) continue;
    bounds.extend(pos);

    const pinHtml = _buildStopMapPin(ent.type, ent.data);
    const popupHtml = _buildStopMapPopup(ent.type, ent.data);
    const infoWindow = new google.maps.InfoWindow({ content: popupHtml });
    const overlay = GoogleMaps.createDivMarker(map, pos, pinHtml, () => {
      if (_openInfoWindow) _openInfoWindow.close();
      infoWindow.setPosition(pos);
      infoWindow.open(map);
      _openInfoWindow = infoWindow;
    });
    attachHover(overlay, infoWindow, pos);
  }

  // Render driving route through time block locations with stop anchors
  if (routePoints.length >= 2) {
    GoogleMaps.renderDrivingRoute(map, routePoints, {
      strokeColor: '#0EA5E9', strokeWeight: 3, strokeOpacity: 0.8,
    }).catch(() => {});
  }

  if (coords.size > 1) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }
}

// ---------------------------------------------------------------------------
// Stops Overview (card grid)
// ---------------------------------------------------------------------------

function renderStopsOverview(plan) {
  const stops = plan.stops || [];
  const cards = stops.map((stop, i) => {
    const flag = FLAGS[stop.country] || '';
    const acc = stop.accommodation || {};
    const actCount = (stop.top_activities || []).length;
    const restCount = (stop.restaurants || []).length;
    return `
      <div class="stop-overview-card" data-stop-id="${stop.id}" draggable="true"
        ondragstart="_onStopDragStart(event, ${i})"
        ondragend="_onStopDragEnd(event)"
        ondragover="event.preventDefault(); this.classList.add('drag-over')"
        ondragleave="this.classList.remove('drag-over')"
        ondrop="_onStopDrop(event, ${i})">
        <div class="stop-overview-card-inner">
          <div class="drag-handle" title="Ziehen zum Sortieren">
            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg>
          </div>
          <div class="stop-overview-card-main">
            ${buildHeroPhotoLoading('sm')}
            <div class="stop-overview-card-body">
              <div class="stop-number">Stop ${stop.id}</div>
              <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
              <div class="stop-meta">
                ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
                ${stop.drive_hours_from_prev > 0 ? ` \u00b7 ${stop.drive_hours_from_prev}h Fahrt` : ''}
                ${stop.drive_km_from_prev > 0 ? ` \u00b7 ${stop.drive_km_from_prev} km` : ''}
              </div>
              <div class="stop-overview-highlights">
                ${acc.name ? `<span class="stop-overview-chip chip-acc">${esc(acc.name)} \u00b7 CHF ${(acc.total_price_chf || 0).toLocaleString('de-CH')}</span>` : ''}
                ${actCount ? `<span class="stop-overview-chip chip-act">${actCount} Aktivit\u00e4t${actCount !== 1 ? 'en' : ''}</span>` : ''}
                ${restCount ? `<span class="stop-overview-chip chip-rest">${restCount} Restaurant${restCount !== 1 ? 's' : ''}</span>` : ''}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="stops-overview-grid">
      ${cards}
    </div>
    <div class="stops-overview-actions">
      <button class="btn btn-primary add-stop-btn" onclick="_openAddStopModal()">+ Stopp hinzuf\u00fcgen</button>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Stop Detail (full page with sidebar + prev/next)
// ---------------------------------------------------------------------------

function renderStopDetail(plan, stopId) {
  const stops = plan.stops || [];
  const dayPlans = plan.day_plans || [];
  const idx = stops.findIndex(s => String(s.id) === String(stopId));
  const stop = stops[idx];
  if (!stop) return renderStopsOverview(plan);

  const flag = FLAGS[stop.country] || '';
  const prev = idx > 0 ? stops[idx - 1] : null;
  const next = idx < stops.length - 1 ? stops[idx + 1] : null;
  const further = stop.further_activities || [];

  // Sidebar items for quick nav
  const sidebarItems = stops.map(s => {
    const f = FLAGS[s.country] || '';
    return `
      <div class="stops-sidebar-item${String(s.id) === String(stopId) ? ' active' : ''}" data-stop-id="${s.id}">
        <span class="sidebar-stop-num">${s.id}</span>
        <span class="sidebar-stop-label">${f} ${esc(s.region)}</span>
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
        <div class="stop-detail-nav">
          <button class="stop-detail-back">\u2190 Alle Stops</button>
          <span class="stop-detail-breadcrumb">Stop ${stop.id}: ${flag} ${esc(stop.region)}</span>
        </div>

        <div class="stop-card" id="guide-stop-${stop.id}" data-stop-id="${stop.id}">
          <div class="stop-detail-header">
            <div class="stop-header-left">
              <div class="stop-number">Stop ${stop.id}</div>
              <h3>${flag} ${esc(stop.region)}, ${esc(stop.country)}</h3>
              <div class="stop-meta">
                Tag ${stop.arrival_day} \u00b7 ${stop.nights} Nacht${stop.nights !== 1 ? 'e' : ''}
                ${stop.drive_hours_from_prev > 0 ? ` \u00b7 ${stop.drive_hours_from_prev}h Fahrt` : ''}
                ${stop.drive_km_from_prev > 0 ? ` \u00b7 ${stop.drive_km_from_prev} km` : ''}
              </div>
            </div>
            <div class="stop-header-right">
              ${stops.length > 1 ? `<button class="remove-stop-btn btn-icon-danger" onclick="event.stopPropagation(); _confirmRemoveStop(${stop.id})" title="Stopp entfernen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                Entfernen
              </button>` : ''}
              <button class="replace-stop-btn" onclick="event.stopPropagation(); openReplaceStopModal(${stop.id}, ${stop.nights})" title="Stopp ersetzen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
                Ersetzen
              </button>
              ${(stop.place_id || stop.google_maps_url) ? `<a href="${safeUrl(stop.place_id ? 'https://www.google.com/maps/place/?q=place_id:' + stop.place_id : stop.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
          </div>

          <div class="stop-body" style="display:block">
            ${buildHeroPhotoLoading('lg')}
            <div class="stop-overview-map" id="stop-map-${stop.id}"></div>
            ${renderTravelGuide(stop.travel_guide)}
            ${_renderAccommodationHtml(stop)}
            ${_renderActivitiesHtml(stop)}
            ${renderFurtherActivities(further)}
            ${_renderRestaurantsHtml(stop)}
            ${_renderDayExamplesHtml(stop, dayPlans)}
          </div>
        </div>

        <div class="stop-detail-prevnext">
          ${prev ? `<button class="btn btn-secondary stop-nav-prev" data-stop-id="${prev.id}">\u2190 Stop ${prev.id}: ${esc(prev.region)}</button>` : '<span></span>'}
          ${next ? `<button class="btn btn-secondary stop-nav-next" data-stop-id="${next.id}">Stop ${next.id}: ${esc(next.region)} \u2192</button>` : '<span></span>'}
        </div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Stop navigation helpers
// ---------------------------------------------------------------------------

function navigateToStop(stopId) {
  _activeStopId = Number(stopId);
  const plan = S.result;
  if (!plan) return;
  renderGuide(plan, 'stops');
  // Update URL
  if (plan._saved_travel_id) {
    const title = plan.custom_name || plan.title || '';
    const base = Router.travelPath(plan._saved_travel_id, title);
    Router.navigate(base + '/stops/' + stopId, { skipDispatch: true });
  }
}

function navigateToStopsOverview() {
  _activeStopId = null;
  const plan = S.result;
  if (!plan) return;
  renderGuide(plan, 'stops');
  // Update URL
  if (plan._saved_travel_id) {
    const title = plan.custom_name || plan.title || '';
    const base = Router.travelPath(plan._saved_travel_id, title);
    Router.navigate(base + '/stops', { skipDispatch: true });
  }
}

function activateStopDetail(stopId) {
  _activeStopId = Number(stopId);
  renderGuide(S.result, 'stops');
}

// One-time event delegation on #guide-content (set up in _initGuideDelegation)
let _guideDelegationReady = false;

function _initGuideDelegation() {
  if (_guideDelegationReady) return;
  _guideDelegationReady = true;
  const root = document.getElementById('guide-content');
  if (!root) return;

  root.addEventListener('click', (e) => {
    // Overview card click → navigate to stop detail
    const overviewCard = e.target.closest('.stop-overview-card');
    if (overviewCard) {
      const stopId = overviewCard.dataset.stopId;
      if (stopId) navigateToStop(stopId);
      return;
    }

    // Back button on detail page → navigate to overview
    const backBtn = e.target.closest('.stop-detail-back');
    if (backBtn) {
      navigateToStopsOverview();
      return;
    }

    // Prev/next navigation on detail page
    const navBtn = e.target.closest('.stop-nav-prev, .stop-nav-next');
    if (navBtn) {
      const stopId = navBtn.dataset.stopId;
      if (stopId) navigateToStop(stopId);
      return;
    }

    // Sidebar item click on detail page → navigate to that stop
    const sidebarItem = e.target.closest('.stops-sidebar-item');
    if (sidebarItem) {
      const stopId = sidebarItem.dataset.stopId;
      if (stopId) navigateToStop(stopId);
      return;
    }

    // Day CTA box in stop detail → navigate to day detail
    const dayCta = e.target.closest('.stop-day-cta');
    if (dayCta) {
      const dayNum = dayCta.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Day overview card → navigate to day detail
    const dayCard = e.target.closest('.day-overview-card');
    if (dayCard) {
      const dayNum = dayCard.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Day detail back → days overview
    const dayBack = e.target.closest('.day-detail-back');
    if (dayBack) {
      navigateToDaysOverview();
      return;
    }

    // Day prev/next navigation
    const dayNav = e.target.closest('.day-nav-prev, .day-nav-next');
    if (dayNav) {
      const dayNum = dayNav.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Days sidebar item → navigate to that day
    const daySidebarItem = e.target.closest('.days-sidebar-item');
    if (daySidebarItem) {
      const dayNum = daySidebarItem.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }
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
  const weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const monthNames = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                      'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

  // Parse date string (DD.MM.YYYY or YYYY-MM-DD) into Date object
  function parseDate(str) {
    if (!str) return null;
    const dotMatch = str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (dotMatch) return new Date(+dotMatch[3], +dotMatch[2] - 1, +dotMatch[1]);
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  }

  // Compute base start date from the first day plan that has a date
  let baseDate = null;
  for (const dp of dayPlans) {
    const d = parseDate(dp.date);
    if (d) {
      baseDate = new Date(d);
      baseDate.setDate(baseDate.getDate() - (dp.day - 1));
      break;
    }
  }

  // Find max day number to detect gaps (missing drive days)
  const dayNums = new Set(dayPlans.map(dp => dp.day));
  const maxDay = dayPlans.reduce((m, dp) => Math.max(m, dp.day), 0);

  // Fill in missing days as drive days
  const allDayPlans = [...dayPlans];
  if (baseDate) {
    for (let d = 1; d <= maxDay; d++) {
      if (!dayNums.has(d)) {
        const driveDate = new Date(baseDate);
        driveDate.setDate(driveDate.getDate() + (d - 1));
        const dd = String(driveDate.getDate()).padStart(2, '0');
        const mm = String(driveDate.getMonth() + 1).padStart(2, '0');
        const yyyy = driveDate.getFullYear();
        allDayPlans.push({ day: d, date: `${dd}.${mm}.${yyyy}`, type: 'drive', title: 'Reisetag', description: '' });
      }
    }
  }

  // Build lookup: date-string (YYYY-MM-DD) → { dp, type, stop, flag, stopName }
  const dayMap = new Map();
  allDayPlans.forEach(dp => {
    const raw = (dp.type || 'mixed').toLowerCase();
    const type = ['drive','rest','activity','mixed'].includes(raw) ? raw : 'mixed';
    const stop = stops.find(s => {
      const arr = s.arrival_day || 1;
      return dp.day >= arr && dp.day < arr + (s.nights || 1);
    });
    const flag = stop ? (FLAGS[stop.country] || '') : '';
    const stopName = stop ? stop.region : '';
    const stopId = stop ? stop.id : null;
    let date = parseDate(dp.date);
    if (!date && baseDate) {
      date = new Date(baseDate);
      date.setDate(date.getDate() + (dp.day - 1));
    }
    if (date) {
      const key = date.toISOString().slice(0, 10);
      dayMap.set(key, { dp, type, stop, flag, stopName, stopId, date });
    }
  });

  // Determine date range
  const allDates = [...dayMap.values()].map(v => v.date).sort((a, b) => a - b);
  if (allDates.length === 0) {
    return `<div class="calendar-section"><p class="calendar-hint">Keine Kalenderdaten verfügbar.</p></div>`;
  }

  const firstDate = allDates[0];
  const lastDate = allDates[allDates.length - 1];

  // Find Monday of the week containing firstDate (0=Sun in JS, we want Mon start)
  function getMonday(d) {
    const dt = new Date(d);
    const day = dt.getDay(); // 0=Sun, 1=Mon, ...
    const diff = day === 0 ? -6 : 1 - day;
    dt.setDate(dt.getDate() + diff);
    return dt;
  }

  const startMon = getMonday(firstDate);
  // Find Sunday of the week containing lastDate
  const endSun = new Date(lastDate);
  const endDay = endSun.getDay();
  if (endDay !== 0) endSun.setDate(endSun.getDate() + (7 - endDay));

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayKey = today.toISOString().slice(0, 10);

  // Build weeks
  let html = '';
  let currentMonth = -1;
  const cursor = new Date(startMon);

  while (cursor <= endSun) {
    // Check if we need a month header
    const weekStart = new Date(cursor);
    // Use the date of the first trip day in this week, or the Monday for month label
    const monthCheckDate = new Date(cursor);
    // Advance to find first day in this week that's part of the trip or just use Monday
    if (monthCheckDate.getMonth() !== currentMonth) {
      currentMonth = monthCheckDate.getMonth();
      html += `<div class="calendar-month-header">${monthNames[currentMonth]} ${monthCheckDate.getFullYear()}</div>`;
    }

    // Build 7 cells for this week
    let weekHtml = '';
    for (let i = 0; i < 7; i++) {
      const dateKey = cursor.toISOString().slice(0, 10);
      const entry = dayMap.get(dateKey);
      const dayNum = cursor.getDate();
      const isToday = dateKey === todayKey;

      if (entry) {
        const { dp, type, flag, stopName, stopId } = entry;
        weekHtml += `
          <div class="calendar-day calendar-day--trip${isToday ? ' calendar-day--today' : ''}"
               data-type="${esc(type)}" data-stop-id="${stopId || ''}" data-day-num="${dp.day}"
               title="${esc(dp.title)}" tabindex="0" role="button">
            <div class="calendar-day__header">
              <span class="calendar-day__num">${dayNum}</span>
              <span class="calendar-day__trip-day">Tag ${dp.day}</span>
            </div>
            <div class="calendar-day__icon">${typeIcon[type] || _pinIcon}</div>
            <div class="calendar-day__title">${esc(dp.title || typeLabel[type])}</div>
            ${stopName ? `<div class="calendar-day__stop">${flag} ${esc(stopName)}</div>` : ''}
          </div>`;
      } else {
        weekHtml += `
          <div class="calendar-day calendar-day--empty${isToday ? ' calendar-day--today' : ''}">
            <span class="calendar-day__num calendar-day__num--empty">${dayNum}</span>
          </div>`;
      }

      cursor.setDate(cursor.getDate() + 1);
    }

    html += `<div class="calendar-week">${weekHtml}</div>`;
  }

  // Weekday header
  const headerHtml = weekdays.map(d => `<div class="calendar-weekday">${d}</div>`).join('');

  return `
    <div class="calendar-section">
      <h3 class="calendar-title">Reise-Kalender</h3>
      <p class="calendar-hint">Klick auf einen Tag öffnet den Tagesplan.</p>
      <div class="calendar-grid-wrap">
        <div class="calendar-weekday-row">${headerHtml}</div>
        ${html}
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
  document.querySelectorAll('.calendar-day--trip[data-day-num]').forEach(cell => {
    const dayNum = cell.dataset.dayNum;
    if (!dayNum) return;
    cell.addEventListener('click', () => {
      navigateToDay(dayNum);
    });
    cell.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); cell.click(); }
    });
  });
}

function _scrollToGuideStop(stopId) {
  navigateToStop(stopId);
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

  // Driving route through all route points (falls back to straight line on error)
  if (routePoints.length >= 2) {
    const guideWaypoints = routePoints.map(pt => ({ lat: pt.lat(), lng: pt.lng() }));
    GoogleMaps.renderDrivingRoute(map, guideWaypoints, {
      strokeColor: '#0EA5E9', strokeWeight: 3, strokeOpacity: 0.8,
    }).then(r => { _guidePolyline = r; });
  }

  if (hasBounds) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
      if (map.getZoom() > 9) map.setZoom(9);
    });
  }
}

// ---------------------------------------------------------------------------
// Persistent guide map + bidirectional sync (D-09, D-11)
// ---------------------------------------------------------------------------

/** Initialize the persistent guide map once. Reuses existing map on subsequent calls. */
function _setupGuideMap(plan) {
  if (typeof GoogleMaps === 'undefined' || !window.google) return;
  const map = GoogleMaps.initPersistentGuideMap('guide-map', { center: { lat: 47, lng: 8 }, zoom: 6 });
  if (!map) return;
  GoogleMaps.setGuideMarkers(plan, _onMarkerClick);
  _guideMapInitialized = true;

  // Suppress auto-pan during user map interaction (Pitfall 4)
  google.maps.event.addListener(map, 'dragstart', () => {
    _userInteractingWithMap = true;
    clearTimeout(_userInteractionTimeout);
  });
  google.maps.event.addListener(map, 'dragend', () => {
    _userInteractionTimeout = setTimeout(() => { _userInteractingWithMap = false; }, 3000);
  });
}

/** Update map view when switching tabs. */
function _updateMapForTab(plan, tab) {
  if (typeof GoogleMaps === 'undefined' || !_guideMapInitialized) return;
  GoogleMaps.fitAllStops(plan);
}

/** Handle marker click: highlight marker and scroll to card. */
function _onMarkerClick(stopId) {
  if (typeof GoogleMaps !== 'undefined') GoogleMaps.highlightGuideMarker(stopId);
  if (activeTab === 'stops') {
    _scrollToAndHighlightCard(stopId);
  } else {
    _activeStopId = null;
    switchGuideTab('stops');
    requestAnimationFrame(() => {
      setTimeout(() => _scrollToAndHighlightCard(stopId), 100);
    });
  }
}

/** Scroll content panel to a stop card and highlight it. */
function _scrollToAndHighlightCard(stopId) {
  const sel = '[data-stop-id="' + stopId + '"]';
  const card = document.querySelector('.stop-card-row' + sel)
    || document.querySelector('.stop-overview-card' + sel);
  if (!card) return;
  document.querySelectorAll('.stop-card-row.selected, .stop-overview-card.selected')
    .forEach(el => el.classList.remove('selected'));
  card.classList.add('selected');
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/** Set up IntersectionObserver on stop cards for auto-pan (D-09). */
function _initScrollSync() {
  if (_cardObserver) _cardObserver.disconnect();
  if (typeof GoogleMaps === 'undefined') return;

  _cardObserver = new IntersectionObserver((entries) => {
    if (_userInteractingWithMap) return;
    const visible = entries.find(e => e.isIntersecting);
    if (!visible) return;
    clearTimeout(_scrollDebounce);
    _scrollDebounce = setTimeout(() => {
      const stopId = visible.target.dataset.stopId;
      if (stopId && stopId !== _lastPannedStopId) {
        _lastPannedStopId = stopId;
        GoogleMaps.panToStop(stopId, S.result?.stops || []);
        GoogleMaps.highlightGuideMarker(stopId);
      }
    }, 300);
  }, { threshold: 0.6 });

  document.querySelectorAll('[data-stop-id]').forEach(card => {
    _cardObserver.observe(card);
  });
}

/**
 * Lazily load images for an entity (stop, activity, restaurant, accommodation)
 * via Google Places and fill the hero-photo skeleton container.
 */
async function _lazyLoadEntityImages(containerEl, placeName, lat, lng, context, sizeClass) {
  const placeholder = containerEl?.querySelector('.hero-photo-loading');
  if (!containerEl || typeof GoogleMaps === 'undefined') {
    if (placeholder) placeholder.remove();
    return;
  }
  // Safety timeout: remove shimmer if image loading hangs
  const timer = placeholder && setTimeout(() => { if (placeholder.isConnected) placeholder.remove(); }, 12000);
  try {
    const urls = await GoogleMaps.getPlaceImages(placeName, lat, lng, context);
    const size = sizeClass || (placeholder?.classList.contains('hero-photo--lg') ? 'lg'
      : placeholder?.classList.contains('hero-photo--sm') ? 'sm' : 'md');
    const isGalleryCompact = placeholder?.classList.contains('hero-gallery-compact');
    const isGallery = placeholder?.classList.contains('hero-gallery');
    const newHtml = isGalleryCompact
      ? buildHeroPhotoGalleryCompact(urls, placeName)
      : isGallery
        ? buildHeroPhotoGallery(urls, placeName, size)
        : buildHeroPhoto(urls, placeName, size);
    clearTimeout(timer);
    if (!newHtml) {
      if (placeholder) placeholder.remove();
      return;
    }
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
    clearTimeout(timer);
    if (placeholder) placeholder.remove();
    if (typeof S !== 'undefined') {
      S.logs.push({ level: 'WARNING', agent: 'GoogleMaps', message: `_lazyLoadEntityImages fehlgeschlagen für «${placeName}»: ${e.message}` });
      if (typeof updateDebugLog === 'function') updateDebugLog();
    }
  }
}

/** Walk the rendered stops section and lazy-load images for all entities. */
// ---------------------------------------------------------------------------
// Stop Overview Maps
// ---------------------------------------------------------------------------

function _getActivityIcon(name) {
  const n = (name || '').toLowerCase();
  if (/museum|galerie|gallery/.test(n)) return '🏛';
  if (/wander|hiking|randonnée/.test(n)) return '🥾';
  if (/see|lac|lake|schwimm|baignade|baden/.test(n)) return '🏊';
  if (/schloss|castle|château|burg|palast|palace/.test(n)) return '🏰';
  if (/park|garten|jardin|garden/.test(n)) return '🌿';
  if (/markt|market|marché/.test(n)) return '🛍';
  if (/kirche|church|église|dom|cathedral/.test(n)) return '⛪';
  if (/ski|snowboard/.test(n)) return '⛷';
  if (/strand|beach|plage/.test(n)) return '🏖';
  if (/wein|vin|wine/.test(n)) return '🍷';
  return '⭐';
}

function _buildStopMapPin(type, entity) {
  if (type === 'hotel') return '<div class="stop-map-pin pin-hotel">🏨</div>';
  if (type === 'activity') return `<div class="stop-map-pin pin-activity">${_getActivityIcon(entity.name)}</div>`;
  if (type === 'restaurant') return '<div class="stop-map-pin pin-restaurant">🍽</div>';
  return '<div class="stop-map-pin pin-activity">📍</div>';
}

function _buildStopMapPopup(type, entity) {
  if (type === 'hotel') {
    const ratingStr = entity.rating ? `${entity.rating}★` : '';
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.type ? esc(entity.type) : ''}
        ${entity.price_per_night_chf ? ` · CHF ${entity.price_per_night_chf}/Nacht` : ''}
        ${ratingStr ? ` · ${ratingStr}` : ''}
      </div>
    </div>`;
  }
  if (type === 'activity') {
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.duration_hours ? entity.duration_hours + 'h' : ''}
        ${entity.price_chf > 0 ? ' · CHF ' + entity.price_chf : ' · kostenlos'}
      </div>
      ${entity.description ? `<div class="popup-desc">${esc(entity.description)}</div>` : ''}
    </div>`;
  }
  if (type === 'restaurant') {
    return `<div class="stop-map-popup">
      <strong>${esc(entity.name)}</strong>
      <div class="popup-meta">
        ${entity.cuisine ? esc(entity.cuisine) : ''}
        ${entity.price_range ? ' · ' + esc(entity.price_range) : ''}
      </div>
      ${entity.family_friendly ? '<div class="popup-badge">Familienfreundlich</div>' : ''}
    </div>`;
  }
  return `<div class="stop-map-popup"><strong>${esc(entity.name || '')}</strong></div>`;
}

function _scrollToAndHighlight(selector, stopId) {
  const container = document.getElementById(`guide-stop-${stopId}`);
  if (!container) return;
  const el = container.querySelector(selector);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('highlight-flash');
  void el.offsetWidth; // reflow to restart animation
  el.classList.add('highlight-flash');
  el.addEventListener('animationend', () => el.classList.remove('highlight-flash'), { once: true });
}

async function _initStopMap(stop) {
  if (!window.google || !google.maps) return;
  if (_initializedStopMaps.has(stop.id)) return;
  _initializedStopMaps.add(stop.id);

  const elId = 'stop-map-' + stop.id;
  const center = { lat: stop.lat || 47, lng: stop.lng || 8 };
  const map = GoogleMaps.initStopOverviewMap(elId, { center, zoom: 13 });
  if (!map) return;

  // Collect ALL entities from this stop (with or without place_id)
  const entities = [];
  const acc = stop.accommodation;
  if (acc && acc.name) {
    entities.push({
      key: `hotel-${stop.id}`,
      placeId: acc.place_id || null,
      name: acc.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'hotel',
      type: 'hotel', data: acc, index: 0,
    });
  }

  (stop.top_activities || []).forEach((act, i) => {
    if (!act.name) return;
    entities.push({
      key: `act-${stop.id}-${i}`,
      placeId: act.place_id || null,
      lat: act.lat || null,
      lng: act.lon || null,
      name: act.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'activity',
      type: 'activity', data: act, index: i,
    });
  });

  (stop.further_activities || []).forEach((act, i) => {
    if (!act.name) return;
    entities.push({
      key: `fact-${stop.id}-${i}`,
      placeId: act.place_id || null,
      lat: act.lat || null,
      lng: act.lon || null,
      name: act.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'activity',
      type: 'activity', data: act, index: i,
      isFurther: true,
    });
  });

  (stop.restaurants || []).forEach((r, i) => {
    if (!r.name) return;
    entities.push({
      key: `rest-${stop.id}-${i}`,
      placeId: r.place_id || null,
      name: r.name,
      stopLat: stop.lat, stopLng: stop.lng,
      searchType: 'restaurant',
      type: 'restaurant', data: r, index: i,
    });
  });

  if (entities.length === 0) return;

  let coords;
  try {
    coords = await GoogleMaps.resolveEntityCoordinates(entities);
  } catch (e) {
    console.error('Stop map coord resolve:', e);
    return;
  }

  if (coords.size === 0) return;

  const bounds = new google.maps.LatLngBounds();
  let _openInfoWindow = null;

  for (const ent of entities) {
    const pos = coords.get(ent.key);
    if (!pos) continue;

    bounds.extend(pos);
    const pinHtml = _buildStopMapPin(ent.type, ent.data);
    const popupHtml = _buildStopMapPopup(ent.type, ent.data);
    const infoWindow = new google.maps.InfoWindow({ content: popupHtml });

    let hoverTimeout = null;

    const overlay = GoogleMaps.createDivMarker(map, pos, pinHtml, () => {
      // Click → scroll to corresponding section
      if (ent.type === 'hotel') {
        _scrollToAndHighlight('.stop-accommodation', stop.id);
      } else if (ent.type === 'activity') {
        if (ent.isFurther) {
          _scrollToAndHighlight('.further-activities', stop.id);
        } else {
          _scrollToAndHighlight(`.activities-grid .activity-card:nth-child(${ent.index + 1})`, stop.id);
        }
      } else if (ent.type === 'restaurant') {
        _scrollToAndHighlight(`.restaurants-list .restaurant-item:nth-child(${ent.index + 1})`, stop.id);
      }
    });

    // Hover behavior — attach to overlay div after it's added
    const origOnAdd = overlay.onAdd;
    overlay.onAdd = function () {
      origOnAdd.call(this);
      const div = this._div;
      if (!div) return;

      div.addEventListener('mouseenter', () => {
        clearTimeout(hoverTimeout);
        if (_openInfoWindow) _openInfoWindow.close();
        infoWindow.setPosition(pos);
        infoWindow.open(map);
        _openInfoWindow = infoWindow;
      });

      div.addEventListener('mouseleave', () => {
        hoverTimeout = setTimeout(() => {
          infoWindow.close();
          if (_openInfoWindow === infoWindow) _openInfoWindow = null;
        }, 150);
      });
    };
  }

  // Fit bounds with padding
  if (coords.size > 1) {
    map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }
}

function _lazyLoadOverviewImages(plan) {
  const stops = plan.stops || [];
  stops.forEach(stop => {
    const card = document.querySelector(`.stop-overview-card[data-stop-id="${stop.id}"]`);
    if (card) _lazyLoadEntityImages(card, stop.region, stop.lat, stop.lng, 'city', 'sm');
  });
}

function _lazyLoadSingleStopImages(plan, stop) {
  const stopEl = document.getElementById(`guide-stop-${stop.id}`);
  if (!stopEl) return;
  const lat = stop.lat;
  const lng = stop.lng;

  _lazyLoadEntityImages(stopEl.querySelector('.stop-detail-header')?.parentElement || stopEl, stop.region, lat, lng, 'city');

  const accEl = stopEl.querySelector('.stop-accommodation');
  if (accEl && stop.accommodation) {
    _lazyLoadEntityImages(accEl, stop.accommodation.name, lat, lng, 'hotel');
    accEl.querySelectorAll('.acc-alt-item').forEach((el, i) => {
      const altOpts = (stop.all_accommodation_options || []).filter(o => o.name !== stop.accommodation.name);
      const o = altOpts[i];
      if (o) _lazyLoadEntityImages(el, o.name, lat, lng, 'hotel');
    });
  }

  stopEl.querySelectorAll('.activity-card').forEach((el, i) => {
    const act = (stop.top_activities || [])[i];
    if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
  });

  stopEl.querySelectorAll('.further-activity-item').forEach((el, i) => {
    const act = (stop.further_activities || [])[i];
    if (act) _lazyLoadEntityImages(el, act.name, lat, lng, 'activity');
  });

  stopEl.querySelectorAll('.restaurant-item').forEach((el, i) => {
    const rest = (stop.restaurants || [])[i];
    if (rest) _lazyLoadEntityImages(el, rest.name, lat, lng, 'restaurant');
  });
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
// Edit Lock — one operation at a time (D-17)
// ---------------------------------------------------------------------------

function _lockEditing() {
  _editInProgress = true;
  document.querySelectorAll('.remove-stop-btn, .add-stop-btn, .replace-stop-btn').forEach(btn => {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.pointerEvents = 'none';
  });
  document.querySelectorAll('.stop-overview-card[draggable]').forEach(card => {
    card.style.opacity = '0.5';
    card.style.pointerEvents = 'none';
  });
}

function _unlockEditing() {
  _editInProgress = false;
  document.querySelectorAll('.remove-stop-btn, .add-stop-btn, .replace-stop-btn').forEach(btn => {
    btn.disabled = false;
    btn.style.opacity = '';
    btn.style.pointerEvents = '';
  });
  document.querySelectorAll('.stop-overview-card[draggable]').forEach(card => {
    card.style.opacity = '';
    card.style.pointerEvents = '';
  });
}

// ---------------------------------------------------------------------------
// Remove Stop — confirm + execute
// ---------------------------------------------------------------------------

function _confirmRemoveStop(stopId) {
  if (_editInProgress) return;
  const plan = S.result;
  if (!plan) return;
  const stop = (plan.stops || []).find(s => s.id === stopId);
  if (!stop) return;

  const existing = document.getElementById('confirm-remove-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'confirm-remove-modal';
  modal.className = 'modal-backdrop';

  // Build modal content safely using esc() for user data
  const heading = document.createElement('h3');
  heading.textContent = 'Stopp entfernen?';

  const para = document.createElement('p');
  para.innerHTML = 'M\u00f6chtest du <strong>' + esc(stop.region) + '</strong> wirklich entfernen? Alle recherchierten Daten (Aktivit\u00e4ten, Restaurants, Unterk\u00fcnfte) gehen verloren.';

  const actions = document.createElement('div');
  actions.className = 'modal-actions';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = 'Abbrechen';
  cancelBtn.onclick = () => modal.remove();

  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn btn-danger';
  removeBtn.textContent = 'Entfernen';
  removeBtn.onclick = () => _executeRemoveStop(stopId);

  actions.appendChild(cancelBtn);
  actions.appendChild(removeBtn);

  const content = document.createElement('div');
  content.className = 'modal-content';
  content.appendChild(heading);
  content.appendChild(para);
  content.appendChild(actions);

  modal.appendChild(content);
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  document.body.appendChild(modal);
}

async function _executeRemoveStop(stopId) {
  const modal = document.getElementById('confirm-remove-modal');
  if (modal) modal.remove();

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  _lockEditing();
  try {
    const res = await apiRemoveStop(travelId, stopId);
    _editSSE = openSSE(res.job_id, {
      remove_stop_progress: () => {},
      remove_stop_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _activeStopId = null;
        _unlockEditing();
        renderGuide(data, 'stops');
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Entfernen: ' + (data.error || 'Unbekannter Fehler'));
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Add Stop — modal + execute
// ---------------------------------------------------------------------------

function _openAddStopModal() {
  if (_editInProgress) return;
  const plan = S.result;
  if (!plan) return;

  const savedId = plan._saved_travel_id;
  if (!savedId) {
    alert('Reise muss zuerst gespeichert werden.');
    return;
  }

  const stops = plan.stops || [];
  const existing = document.getElementById('add-stop-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'add-stop-modal';
  modal.className = 'modal-backdrop';

  const content = document.createElement('div');
  content.className = 'modal-content';

  const heading = document.createElement('h3');
  heading.textContent = 'Stopp hinzuf\u00fcgen';
  content.appendChild(heading);

  // Location input
  const locGroup = document.createElement('div');
  locGroup.className = 'form-group';
  const locLabel = document.createElement('label');
  locLabel.textContent = 'Ort';
  locLabel.setAttribute('for', 'add-stop-location');
  const locInput = document.createElement('input');
  locInput.type = 'text';
  locInput.id = 'add-stop-location';
  locInput.className = 'form-input';
  locInput.placeholder = 'z.B. Lyon, Marseille...';
  locGroup.appendChild(locLabel);
  locGroup.appendChild(locInput);
  content.appendChild(locGroup);

  // Insert-after select
  const afterGroup = document.createElement('div');
  afterGroup.className = 'form-group';
  const afterLabel = document.createElement('label');
  afterLabel.textContent = 'Einf\u00fcgen nach';
  afterLabel.setAttribute('for', 'add-stop-after');
  const afterSelect = document.createElement('select');
  afterSelect.id = 'add-stop-after';
  afterSelect.className = 'form-input';
  stops.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.region + ' (Stop ' + s.id + ')';
    afterSelect.appendChild(opt);
  });
  afterGroup.appendChild(afterLabel);
  afterGroup.appendChild(afterSelect);
  content.appendChild(afterGroup);

  // Nights input
  const nightsGroup = document.createElement('div');
  nightsGroup.className = 'form-group';
  const nightsLabel = document.createElement('label');
  nightsLabel.textContent = 'N\u00e4chte';
  nightsLabel.setAttribute('for', 'add-stop-nights');
  const nightsInput = document.createElement('input');
  nightsInput.type = 'number';
  nightsInput.id = 'add-stop-nights';
  nightsInput.className = 'form-input';
  nightsInput.value = '1';
  nightsInput.min = '1';
  nightsInput.max = '14';
  nightsInput.style.width = '80px';
  nightsGroup.appendChild(nightsLabel);
  nightsGroup.appendChild(nightsInput);
  content.appendChild(nightsGroup);

  // Actions
  const actions = document.createElement('div');
  actions.className = 'modal-actions';
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = 'Abbrechen';
  cancelBtn.onclick = () => modal.remove();
  const addBtn = document.createElement('button');
  addBtn.className = 'btn btn-primary';
  addBtn.textContent = 'Hinzuf\u00fcgen';
  addBtn.onclick = () => _executeAddStop();
  actions.appendChild(cancelBtn);
  actions.appendChild(addBtn);
  content.appendChild(actions);

  modal.appendChild(content);
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  document.body.appendChild(modal);
  setTimeout(() => locInput.focus(), 100);
}

async function _executeAddStop() {
  const location = (document.getElementById('add-stop-location')?.value || '').trim();
  if (!location) { alert('Bitte Ortsnamen eingeben'); return; }

  const afterId = parseInt(document.getElementById('add-stop-after')?.value) || 1;
  const nights = parseInt(document.getElementById('add-stop-nights')?.value) || 1;

  const modal = document.getElementById('add-stop-modal');
  if (modal) modal.remove();

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  _lockEditing();
  try {
    const res = await apiAddStop(travelId, afterId, location, nights);
    _editSSE = openSSE(res.job_id, {
      add_stop_progress: () => {},
      add_stop_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _unlockEditing();
        renderGuide(data, 'stops');
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Hinzuf\u00fcgen: ' + (data.error || 'Unbekannter Fehler'));
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Drag-and-Drop Reorder
// ---------------------------------------------------------------------------

function _onStopDragStart(e, index) {
  if (_editInProgress) { e.preventDefault(); return; }
  _dragStopSourceIndex = index;
  e.dataTransfer.effectAllowed = 'move';
  e.currentTarget.classList.add('dragging');
}

function _onStopDragEnd(e) {
  e.currentTarget.classList.remove('dragging');
}

async function _onStopDrop(e, targetIndex) {
  e.preventDefault();
  document.querySelectorAll('.stop-overview-card').forEach(c => {
    c.classList.remove('drag-over');
    c.classList.remove('dragging');
  });

  if (_dragStopSourceIndex === null || _dragStopSourceIndex === targetIndex) {
    _dragStopSourceIndex = null;
    return;
  }

  const travelId = S.result._saved_travel_id || S.result.id;
  if (!travelId) return;

  const oldIdx = _dragStopSourceIndex;
  _dragStopSourceIndex = null;

  _lockEditing();
  try {
    const res = await apiReorderStops(travelId, oldIdx, targetIndex);
    _editSSE = openSSE(res.job_id, {
      reorder_stops_progress: () => {},
      reorder_stops_complete: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        data._saved_travel_id = travelId;
        S.result = data;
        lsSet(LS_RESULT, { savedAt: new Date().toISOString(), plan: data });
        _unlockEditing();
        renderGuide(data, 'stops');
      },
      job_error: (data) => {
        if (_editSSE) { _editSSE.close(); _editSSE = null; }
        _unlockEditing();
        alert('Fehler beim Sortieren: ' + (data.error || 'Unbekannter Fehler'));
      },
    });
  } catch (err) {
    _unlockEditing();
    alert('Fehler: ' + err.message);
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
          <label>Vorlieben (optional)</label>
          <input type="text" id="replace-stop-hints" class="replace-input" placeholder="z.B. mehr Strand, weniger Fahrzeit..." />
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
  const hints = (document.getElementById('replace-stop-hints')?.value || '').trim();
  if (!loc) { alert('Bitte einen Ort eingeben.'); return; }

  const btn = document.getElementById('replace-manual-btn');
  if (btn) btn.disabled = true;
  _lockEditing();
  _showReplaceProgress('Ort wird gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'manual', loc, nights, hints);
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
  const hints = (document.getElementById('replace-stop-hints')?.value || '').trim();
  _lockEditing();
  _showReplaceProgress('Alternativen werden gesucht…');

  try {
    const res = await apiReplaceStop(travelId, stopId, 'search', null, null, hints);
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
      _unlockEditing();
      closeReplaceStopModal();
      renderGuide(data, activeTab);
    },
    job_error: (data) => {
      if (_replaceStopSSE) { _replaceStopSSE.close(); _replaceStopSSE = null; }
      _unlockEditing();
      _hideReplaceProgress();
      alert('Fehler beim Ersetzen: ' + (data.error || 'Unbekannter Fehler'));
    },
    debug_log: (data) => {
      if (data.message) _showReplaceProgress(data.message);
    },
  });
}
