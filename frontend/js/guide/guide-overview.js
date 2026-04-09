// Guide Overview — overview tab rendering.
// Reads: S (state.js), esc() (state.js).
// Provides: renderOverview, renderTripAnalysis, renderProse, renderTravelGuide,
//           renderFurtherActivities, renderBudget, _lazyLoadOverviewImages,
//           _highlightReqKeywords, _extractReqKeywords, _renderReqTags
'use strict';

/** Renders the full overview tab HTML: header, day-card grid, and collapsible details. */
function renderOverview(plan) {
  const stops = plan.stops || [];
  const cost  = plan.cost_estimate || {};
  const mapUrl = plan.google_maps_overview_url || '';
  const dayPlans = plan.day_plans || [];
  const lastStop = stops[stops.length - 1] || {};

  // SVG car icon for travel days
  const carIcon = '<svg class="day-card-v2__car-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<rect x="1" y="6" width="15" height="10" rx="2"/>' +
    '<path d="M16 10h4l3 4v3h-7V10z"/>' +
    '<circle cx="5.5" cy="18.5" r="2.5"/>' +
    '<circle cx="18.5" cy="18.5" r="2.5"/>' +
    '</svg>';

  // Day cards HTML
  const dayCardsHtml = dayPlans.map(function(dp) {
    const dayStops = _findStopsForDay(plan, dp.day);
    const stopCount = dayStops.length;
    const driveHours = dayStops.reduce(function(sum, s) {
      return sum + (typeof s.drive_hours_from_prev === 'number' ? s.drive_hours_from_prev : 0);
    }, 0);

    // A day is a "travel day" when driving takes up a significant portion (> 3h)
    const isTravelDay = driveHours > 3;

    // Pick most interesting photo subject — time blocks first (day-specific), then stop activities
    const photoSubject = _pickDayPhotoSubject(dp, dayStops);

    return '<div class="day-card-v2' + (isTravelDay ? ' day-card-v2--travel' : '') + '" data-day-num="' + dp.day + '" tabindex="0" role="button">' +
      '<div class="day-card-v2__thumb">' + buildHeroPhotoLoading('sm') + '</div>' +
      (isTravelDay ? '<div class="day-card-v2__ribbon">Fahrtag</div>' + carIcon : '') +
      '<div class="day-card-v2__body">' +
        '<div class="day-card-v2__title">Tag ' + dp.day + ': ' + esc(dp.title) + '</div>' +
        '<div class="day-card-v2__meta">' + stopCount + ' Stopp' + (stopCount !== 1 ? 's' : '') + ' · ' + driveHours.toFixed(1) + 'h Fahrt</div>' +
      '</div>' +
    '</div>';
  }).join('');

  // Collapsible details content
  const detailsContent = renderTripAnalysis(plan.trip_analysis, plan.request) +
    renderBudget(plan) +
    (plan.travel_guide ? renderTravelGuide(plan.travel_guide) : '') +
    renderFurtherActivities(plan.further_activities || []);

  return '<div class="overview-section">' +
    '<div style="margin-bottom:var(--space-lg)">' +
      '<h2 style="font-size:1.75rem;font-weight:600;margin-bottom:var(--space-xs)">' +
        'Reise: ' + esc(plan.start_location) + ' → ' + esc(lastStop.region || '') +
      '</h2>' +
      '<p style="font-size:var(--text-sm);color:var(--text-secondary)">' +
        stops.length + ' Stops · ' + dayPlans.length + ' Tage' +
        (typeof cost.total_chf === 'number' ? ' · CHF ' + cost.total_chf.toLocaleString('de-CH') : '') +
      '</p>' +
      (mapUrl ? '<a href="' + safeUrl(mapUrl) + '" target="_blank" class="btn btn-secondary" style="margin-top:var(--space-sm)">' + t('guide.open_google_maps') + '</a>' : '') +
    '</div>' +
    (dayCardsHtml ? '<div class="day-cards-grid">' + dayCardsHtml + '</div>' : '') +
    '<div class="overview-collapsible">' +
      '<button class="overview-collapsible__toggle" aria-expanded="false">' +
        '<span class="overview-collapsible__chevron">▸</span>' +
        'Reisedetails &amp; Analyse' +
      '</button>' +
      '<div class="overview-collapsible__body">' +
        '<div>' + detailsContent + '</div>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function _initOverviewInteractions(plan) {
  // 1. Collapsible toggle
  var toggle = document.querySelector('.overview-collapsible__toggle');
  if (toggle) {
    toggle.addEventListener('click', function() {
      var collapsible = toggle.closest('.overview-collapsible');
      if (!collapsible) return;
      var expanded = collapsible.classList.toggle('is-expanded');
      toggle.setAttribute('aria-expanded', String(expanded));
      var chevron = toggle.querySelector('.overview-collapsible__chevron');
      if (chevron) chevron.textContent = expanded ? '▾' : '▸';
    });
  }

  // 2. Day card thumbnail lazy loading — uses most interesting entity per day
  var cards = document.querySelectorAll('.day-card-v2');
  var dayPlansMap = {};
  (plan.day_plans || []).forEach(function(dp) { dayPlansMap[dp.day] = dp; });
  cards.forEach(function(card) {
    var dayNum = Number(card.dataset.dayNum);
    var dayStops = _findStopsForDay(plan, dayNum);
    var dp = dayPlansMap[dayNum] || null;
    var subject = _pickDayPhotoSubject(dp, dayStops);
    var thumb = card.querySelector('.day-card-v2__thumb');
    if (thumb && subject) {
      _lazyLoadEntityImages(thumb, subject.name, subject.lat, subject.lng, subject.context, 'sm');
    }
  });

  // 3. Lazy load further activities images inside collapsible
  _lazyLoadOverviewImages(plan);
}

// ---------------------------------------------------------------------------
// Photo subject selection
// ---------------------------------------------------------------------------

/**
 * Picks the most visually interesting photo subject for a day's card thumbnail.
 * Uses day_plan time blocks first (day-specific) so multi-day stops show different photos.
 * Priority: time block with place_id > activity time block > stop activity with place_id >
 *           any stop activity > hotel > region/city fallback.
 * Returns { name, lat, lng, context } or null.
 */
function _pickDayPhotoSubject(dp, dayStops) {
  const refStop = dayStops[0] || {};
  const refLat = refStop.lat || null;
  const refLng = refStop.lng || null;

  // Time blocks are day-specific — prefer them so each day gets a unique photo
  const timeBlocks = (dp && dp.time_blocks) ? dp.time_blocks : [];
  const interestingBlocks = timeBlocks.filter(tb =>
    tb.activity_type !== 'drive' && tb.activity_type !== 'break' &&
    (tb.location || tb.place_id)
  );

  // Best: time block with place_id
  const tbWithId = interestingBlocks.find(tb => tb.place_id);
  if (tbWithId) {
    const ctx = tbWithId.activity_type === 'meal' ? 'restaurant'
              : tbWithId.activity_type === 'check_in' ? 'hotel' : 'activity';
    return { name: tbWithId.location || tbWithId.title, lat: refLat, lng: refLng, context: ctx };
  }

  // Good: any interesting time block
  if (interestingBlocks.length > 0) {
    const tb = interestingBlocks[0];
    const ctx = tb.activity_type === 'meal' ? 'restaurant'
              : tb.activity_type === 'check_in' ? 'hotel' : 'activity';
    return { name: tb.location || tb.title, lat: refLat, lng: refLng, context: ctx };
  }

  // Fallback to stop-level activities (same for all days at a stop, but better than city)
  const activities = dayStops.flatMap(s => (s.top_activities || []).map(a => ({ a, s })));
  const withPlaceId = activities.find(({ a }) => a.place_id);
  if (withPlaceId) {
    const { a, s } = withPlaceId;
    return { name: a.name, lat: a.lat || s.lat, lng: a.lon || a.lng || s.lng, context: 'activity' };
  }
  if (activities.length > 0) {
    const { a, s } = activities[0];
    return { name: a.name, lat: a.lat || s.lat, lng: a.lon || a.lng || s.lng, context: 'activity' };
  }

  // Hotel
  for (const stop of dayStops) {
    if (stop.accommodation && stop.accommodation.name) {
      return { name: stop.accommodation.name, lat: stop.lat, lng: stop.lng, context: 'hotel' };
    }
  }

  // Last resort: region/city
  if (refStop.region || refStop.name) {
    return { name: refStop.region || refStop.name, lat: refLat, lng: refLng, context: 'city' };
  }

  return null;
}

// Highlight requirement keywords (from plan.request) in an already-escaped string
/** Wraps matching keywords in an already-escaped string with highlight spans. */
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
/** Extracts highlight keywords from the TravelRequest (styles, activities, tags). */
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
/** Returns HTML for the request-summary tag pills shown in the trip analysis section. */
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

/** Renders the trip analysis block with match score, requirement tags, and prose. */
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
        <h4>Anforderungserf\u00fcllung</h4>
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
        <h4>St\u00e4rken &amp; Schw\u00e4chen</h4>
        <div class="trip-analysis-swot">
          ${strengths  ? `<div><p class="swot-col-title strengths-title">St\u00e4rken</p><ul class="swot-list strengths-list">${strengths}</ul></div>`  : ''}
          ${weaknesses ? `<div><p class="swot-col-title weaknesses-title">Schw\u00e4chen</p><ul class="swot-list weaknesses-list">${weaknesses}</ul></div>` : ''}
        </div>
      </div>
      ` : ''}

      ${suggestions ? `
      <div class="trip-analysis-card">
        <h4>Verbesserungsvorschl\u00e4ge</h4>
        <div class="suggestions-list">${suggestions}</div>
      </div>
      ` : ''}
    </div>
  `;
}

/** Converts double-newline-separated plain text into escaped paragraph HTML. */
function renderProse(text) {
  if (!text) return '';
  return text.split(/\n\n+/).map(p => `<p>${esc(p.trim())}</p>`).join('');
}

/** Renders the region travel-guide sections (history, food, tips, etc.) as collapsible cards. */
function renderTravelGuide(guide) {
  if (!guide) return '';
  const sections = [
    { key: 'history_culture',  label: 'Geschichte & Kultur' },
    { key: 'food_specialties', label: 'Lokale Spezialit\u00e4ten' },
    { key: 'local_tips',       label: 'Praktische Tipps' },
    { key: 'insider_gems',     label: 'Insider-Tipps' },
    { key: 'best_time_to_visit', label: 'Beste Reisezeit' },
  ];
  return `
    <div class="reisefuehrer-section">
      <h4 class="reisefuehrer-title">Reisef\u00fchrer</h4>
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

/** Renders the "further activities" recommendation list for the overview tab. */
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
                ${act.price_chf > 0 ? ` \u00b7 CHF ${act.price_chf}` : ' \u00b7 kostenlos'}
                ${act.age_group ? ` \u00b7 ${esc(act.age_group)}` : (act.suitable_for_children ? ' \u00b7 familienfreundlich' : '')}
              </div>
              ${(act.place_id || act.google_maps_url) ? `<a href="${safeUrl(act.place_id ? `https://www.google.com/maps/place/?q=place_id:${act.place_id}` : act.google_maps_url)}" target="_blank" class="maps-link">Maps</a>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

/** Renders the budget breakdown tab/section with per-stop cost rows and totals. */
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
    { label: 'Aktivit\u00e4ten', value: act,   color: '#22C55E' },
    { label: 'Verpflegung', value: food,  color: '#F59E0B' },
    { label: 'Treibstoff',  value: fuel,  color: '#EF4444' },
    { label: 'F\u00e4hren',      value: ferry, color: '#5856d6' },
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
    </div>
  `;
}

/** Lazy-loads city images into stop overview cards using IntersectionObserver. */
function _lazyLoadOverviewImages(plan) {
  const stops = plan.stops || [];
  stops.forEach(stop => {
    const card = document.querySelector(`.stop-overview-card[data-stop-id="${stop.id}"]`);
    if (card) _lazyLoadEntityImages(card, stop.region, stop.lat, stop.lng, 'city', 'sm');
  });
}
