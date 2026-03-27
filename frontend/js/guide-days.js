// Guide Days — day overview, day detail, calendar, time blocks.
// Reads: S (state.js), esc() (state.js), activeTab/_activeDayNum (guide-core.js).
// Provides: renderDaysOverview, renderDayDetail, navigateToDay, navigateToDaysOverview,
//           activateDayDetail, _initDayDetailMap, _toggleDayExpand, _findStopsForDay,
//           renderDayTimeBlocks, _renderAccommodationHtml, _renderActivitiesHtml,
//           _renderRestaurantsHtml, _renderDayExamplesHtml, renderCalendar, _initCalendarClicks
'use strict';

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
  if (!dayPlans.length) return '<p class="day-timeline-empty">Keine Tagesplaene vorhanden.</p>';

  const typeLabel = { drive: 'Fahrt', rest: 'Entspannen', activity: 'Erlebnis', mixed: 'Gemischt' };
  const chevronSvg = '<svg class="day-expand-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16"><polyline points="9 6 15 12 9 18"/></svg>';

  const items = dayPlans.map(dp => {
    const type = (dp.type || 'mixed').toLowerCase();
    const dayStops = _findStopsForDay(plan, dp.day);

    // Build summary: "Start nach End -- Xh Fahrt"
    let summaryText = '';
    if (dayStops.length >= 2) {
      summaryText = `${esc(dayStops[0].region || dayStops[0].name)} nach ${esc(dayStops[dayStops.length - 1].region || dayStops[dayStops.length - 1].name)}`;
    } else if (dayStops.length === 1) {
      summaryText = esc(dayStops[0].region || dayStops[0].name);
    }
    // Calculate total drive hours from time blocks
    const driveBlocks = (dp.time_blocks || []).filter(tb => tb.activity_type === 'drive');
    const driveMinutes = driveBlocks.reduce((sum, tb) => sum + (tb.duration_minutes || 0), 0);
    if (driveMinutes > 0) {
      const hrs = (driveMinutes / 60).toFixed(1).replace('.0', '');
      summaryText += (summaryText ? ' \u2014 ' : '') + hrs + 'h Fahrt';
    }

    // Expanded detail: title, description, time blocks
    const detailHtml = `
      <h3>${esc(dp.title)}</h3>
      ${dp.description ? '<p>' + esc(dp.description) + '</p>' : ''}
      ${dp.stops_on_route && dp.stops_on_route.length ? '<div class="day-overview-route">' + dp.stops_on_route.map(s => '<span class="day-route-tag">' + esc(s) + '</span>').join(' \u2192 ') + '</div>' : ''}
      ${renderDayTimeBlocks(dp)}
    `;

    return `
      <div class="day-timeline-item" data-day="${dp.day}">
        <div class="day-timeline-node"></div>
        <div class="day-timeline-content">
          <div class="day-timeline-header" role="listitem" aria-expanded="false" data-day-num="${dp.day}">
            <span class="day-timeline-num">Tag ${dp.day}</span>
            <span class="day-timeline-summary">${summaryText}</span>
            <span class="day-type-badge type-${esc(type)}">${typeLabel[type] || esc(dp.type)}</span>
            ${chevronSvg}
          </div>
          <div class="day-timeline-detail" id="day-detail-${dp.day}" style="display:none">
            ${detailHtml}
          </div>
        </div>
      </div>
    `;
  }).join('');

  return '<div class="day-timeline" role="list">' + items + '</div>';
}

function _toggleDayExpand(dayNum) {
  const detail = document.getElementById('day-detail-' + dayNum);
  if (!detail) return;
  const header = detail.previousElementSibling;
  const isExpanded = detail.style.display !== 'none';
  // Collapse all others first
  document.querySelectorAll('.day-timeline-detail').forEach(d => {
    d.style.display = 'none';
    if (d.previousElementSibling) {
      d.previousElementSibling.setAttribute('aria-expanded', 'false');
      const chev = d.previousElementSibling.querySelector('.day-expand-chevron');
      if (chev) chev.classList.remove('rotated');
    }
  });
  if (!isExpanded) {
    detail.style.display = 'block';
    if (header) {
      header.setAttribute('aria-expanded', 'true');
      const chev = header.querySelector('.day-expand-chevron');
      if (chev) chev.classList.add('rotated');
    }
    detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
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

