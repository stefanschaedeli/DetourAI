// Guide Core — entry point, tab switching, stats, delegation.
// Reads: S (state.js), Router (router.js).
// Provides: showTravelGuide, renderGuide, switchGuideTab, activateGuideTab,
//           renderStatsBar, loadGuideFromCache, _initGuideDelegation, replanCurrentTravel
'use strict';

let activeTab = 'overview';
let _activeStopId = null;
let _activeDayNum = null;

// One-time event delegation on #guide-content
let _guideDelegationReady = false;

// One-time event delegation on #guide-breadcrumb (outside #guide-content)
let _breadcrumbDelegationReady = false;

// Crossfade transition timer — guards against rapid navigation (Pitfall 2)
let _drillTransitionTimer = null;

function showTravelGuide(plan) {
  S.result = plan;

  // Shared mode handling
  if (S.sharedMode) {
    document.body.classList.add('shared-mode');
    const shareCont = document.getElementById('share-toggle-container');
    if (shareCont) shareCont.style.display = 'none';
    // Hide sidebar in shared mode
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.style.display = 'none';
  } else {
    document.body.classList.remove('shared-mode');
    // Show sidebar
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.style.display = '';
    // Show share toggle for saved trips
    if (plan._saved_travel_id) {
      const shareCont = document.getElementById('share-toggle-container');
      if (shareCont) {
        shareCont.style.display = '';
        shareCont.textContent = '';
        const tmp = document.createElement('div');
        tmp.insertAdjacentHTML('afterbegin', _renderShareToggle(plan._saved_travel_id, plan.share_token || null));
        while (tmp.firstChild) shareCont.appendChild(tmp.firstChild);
      }
    }
    // Show replan button for saved trips
    const replanBtn = document.getElementById('replan-current-btn');
    if (replanBtn && plan._saved_travel_id) replanBtn.style.display = '';
  }

  if (typeof updateSidebar === 'function' && !S.sharedMode) updateSidebar();
  _setupGuideMap(plan);
  renderGuide(plan, activeTab);

  // Append shared footer if in shared mode
  if (S.sharedMode) {
    const content = document.getElementById('guide-content');
    if (content && !content.querySelector('.shared-footer')) {
      const footer = document.createElement('div');
      footer.className = 'shared-footer';
      footer.textContent = t('guide.created_with');
      content.appendChild(footer);
    }
  }

  // Pre-populate sidebar overlay content (D-03)
  if (typeof _populateSidebarOverlay === 'function' && !S.sharedMode) _populateSidebarOverlay();
}

function renderGuide(plan, tab) {
  activeTab = tab || 'overview';

  // Wire breadcrumb delegation on first call (breadcrumb is outside #guide-content)
  _initBreadcrumbDelegation();

  // Update tab buttons
  document.querySelectorAll('.guide-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === activeTab);
  });

  const content = document.getElementById('guide-content');
  if (!content) return;

  // Update stats bar -- show on all tabs unconditionally
  // Note: renderStatsBar output uses esc() for all user content (XSS-safe)
  const statsBarEl = document.getElementById('guide-stats-bar');
  if (statsBarEl) {
    statsBarEl.textContent = '';
    const tmp = document.createElement('div');
    tmp.insertAdjacentHTML('afterbegin', renderStatsBar(plan));
    while (tmp.firstChild) statsBarEl.appendChild(tmp.firstChild);
  }

  switch (activeTab) {
    case 'overview':
      content.textContent = '';
      (function() {
        var tmp = document.createElement('div');
        tmp.insertAdjacentHTML('afterbegin', renderOverview(plan));
        while (tmp.firstChild) content.appendChild(tmp.firstChild);
      })();
      _renderBreadcrumb('overview', plan, null, null);
      requestAnimationFrame(function() {
        _initGuideDelegation();
        if (typeof _initOverviewInteractions === 'function') _initOverviewInteractions(plan);
      });
      break;
    case 'stops':
      _initializedStopMaps = new Set();
      if (_activeStopId !== null) {
        content.innerHTML = renderStopDetail(plan, _activeStopId);
        _renderBreadcrumb('stop', plan, _activeDayNum, _activeStopId);
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
        _renderBreadcrumb('overview', plan, null, null);
        requestAnimationFrame(() => {
          _initGuideDelegation();
          _lazyLoadCardImages(plan);
          _initScrollSync();
        });
      }
      break;
    case 'calendar':
      content.innerHTML = renderCalendar(plan);
      _renderBreadcrumb('overview', plan, null, null);
      _initCalendarClicks(plan);
      break;
    case 'days':
      if (_activeDayNum !== null) {
        // Note: innerHTML usage is XSS-safe — all user content passed through esc()
        content.innerHTML = renderDayDetail(plan, _activeDayNum);
        _renderBreadcrumb('day', plan, _activeDayNum, null);
        requestAnimationFrame(() => {
          _initGuideDelegation();
          _initDayDetailMap(plan, _activeDayNum);
        });
      } else {
        content.innerHTML = renderDaysOverview(plan);
        _renderBreadcrumb('overview', plan, null, null);
        requestAnimationFrame(() => _initGuideDelegation());
      }
      break;
    case 'budget':
      content.innerHTML = renderBudget(plan);
      _renderBreadcrumb('overview', plan, null, null);
      break;
    default:
      content.textContent = '';
      (function() {
        var tmp = document.createElement('div');
        tmp.insertAdjacentHTML('afterbegin', renderOverview(plan));
        while (tmp.firstChild) content.appendChild(tmp.firstChild);
      })();
      _renderBreadcrumb('overview', plan, null, null);
      requestAnimationFrame(function() {
        _initGuideDelegation();
        if (typeof _initOverviewInteractions === 'function') _initOverviewInteractions(plan);
      });
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

// ---------------------------------------------------------------------------
// Stats Bar (D-04) — 4 pill widgets at top of overview
// ---------------------------------------------------------------------------

function renderStatsBar(plan) {
  const stops = plan.stops || [];
  const cost = plan.cost_estimate || {};
  const totalDays = plan.day_plans ? plan.day_plans.length : 0;
  const totalStops = stops.length;
  const totalKm = stops.reduce(function (sum, s) {
    return sum + (typeof s.drive_km_from_prev === 'number' ? s.drive_km_from_prev : 0);
  }, 0);
  const budgetRemaining = typeof cost.budget_remaining_chf === 'number' ? cost.budget_remaining_chf : null;
  const budgetNeg = budgetRemaining !== null && budgetRemaining < 0;

  return '<div class="stats-bar">' +
    '<div class="stat-pill"><span class="stat-num">' + totalDays + '</span><span class="stat-label">Tage</span></div>' +
    '<div class="stat-pill"><span class="stat-num">' + totalStops + '</span><span class="stat-label">Stopps</span></div>' +
    '<div class="stat-pill"><span class="stat-num">' + totalKm.toLocaleString('de-CH') + '</span><span class="stat-label">km</span></div>' +
    '<div class="stat-pill' + (budgetNeg ? ' stat-negative' : '') + '"><span class="stat-num">' +
      (budgetRemaining !== null ? 'CHF ' + budgetRemaining.toLocaleString('de-CH') : '\u2013') +
    '</span><span class="stat-label">Budget</span></div>' +
  '</div>';
}

// ---------------------------------------------------------------------------
// Crossfade Drill Transition (D-03, D-04)
// ---------------------------------------------------------------------------

function _drillTransition(renderFn, afterRenderFn) {
  var content = document.getElementById('guide-content');
  if (!content) return;

  // Cancel any in-progress transition (Pitfall 2 guard)
  if (_drillTransitionTimer) {
    clearTimeout(_drillTransitionTimer);
    _drillTransitionTimer = null;
  }

  // Phase 1: fade out
  content.style.transition = 'opacity 0.15s ease-in';
  content.style.opacity = '0';
  content.style.pointerEvents = 'none';

  _drillTransitionTimer = setTimeout(function() {
    _drillTransitionTimer = null;

    // Scroll to top (D-04)
    content.scrollTop = 0;
    var panel = document.getElementById('guide-content-panel');
    if (panel) panel.scrollTop = 0;

    // Render new content via safe DOM pattern
    var html = renderFn();
    content.textContent = '';
    var tmp = document.createElement('div');
    tmp.insertAdjacentHTML('afterbegin', html);
    while (tmp.firstChild) content.appendChild(tmp.firstChild);

    // Phase 2: fade in
    content.style.opacity = '0';
    content.style.transition = '';
    requestAnimationFrame(function() {
      content.style.transition = 'opacity 0.25s ease-out';
      content.style.opacity = '1';
      content.style.pointerEvents = '';
      if (afterRenderFn) afterRenderFn();
    });
  }, 150);
}

// ---------------------------------------------------------------------------
// Breadcrumb Renderer (D-06)
// ---------------------------------------------------------------------------

function _renderBreadcrumb(level, plan, dayNum, stopId) {
  var bar = document.getElementById('guide-breadcrumb');
  if (!bar) return;

  if (level === 'overview') {
    bar.style.display = 'none';
    bar.textContent = '';
    return;
  }

  bar.style.display = '';
  bar.textContent = '';

  // First segment: always "Übersicht"
  var seg1 = document.createElement('span');
  seg1.className = 'guide-breadcrumb__segment';
  seg1.textContent = t('guide.breadcrumb_overview');
  seg1.dataset.navLevel = 'overview';
  seg1.setAttribute('role', 'link');
  seg1.setAttribute('tabindex', '0');
  bar.appendChild(seg1);

  if (level === 'day' && dayNum != null) {
    var sep1 = document.createElement('span');
    sep1.className = 'guide-breadcrumb__separator';
    sep1.textContent = '›';
    bar.appendChild(sep1);

    var dp = (plan.day_plans || []).find(function(d) { return d.day === Number(dayNum); });
    var activeSeg = document.createElement('span');
    activeSeg.className = 'guide-breadcrumb__segment guide-breadcrumb__segment--active';
    activeSeg.textContent = t('guide.breadcrumb_day', {day: dayNum, title: dp && dp.title ? ': ' + dp.title : ''});
    bar.appendChild(activeSeg);
  }

  if (level === 'stop' && stopId != null) {
    var sep2 = document.createElement('span');
    sep2.className = 'guide-breadcrumb__separator';
    sep2.textContent = '›';
    bar.appendChild(sep2);

    var belongsDayNum = dayNum;
    var stop = (plan.stops || []).find(function(s) { return String(s.id) === String(stopId); });
    if (stop && belongsDayNum == null) belongsDayNum = stop.arrival_day;

    var daySeg = document.createElement('span');
    daySeg.className = 'guide-breadcrumb__segment';
    daySeg.textContent = t('guide.breadcrumb_day', {day: belongsDayNum, title: ''});
    daySeg.dataset.navLevel = 'day';
    daySeg.dataset.dayNum = String(belongsDayNum);
    daySeg.setAttribute('role', 'link');
    daySeg.setAttribute('tabindex', '0');
    bar.appendChild(daySeg);

    var sep3 = document.createElement('span');
    sep3.className = 'guide-breadcrumb__separator';
    sep3.textContent = '›';
    bar.appendChild(sep3);

    var stopSeg = document.createElement('span');
    stopSeg.className = 'guide-breadcrumb__segment guide-breadcrumb__segment--active';
    stopSeg.textContent = stop ? (stop.region || stop.name || '') : '';
    bar.appendChild(stopSeg);
  }
}

function _initGuideDelegation() {
  if (_guideDelegationReady) return;
  _guideDelegationReady = true;
  const root = document.getElementById('guide-content');
  if (!root) return;

  root.addEventListener('click', (e) => {
    // Overview card click - navigate to stop detail (legacy + new layout)
    const overviewCard = e.target.closest('.stop-overview-card');
    if (overviewCard) {
      const stopId = overviewCard.dataset.stopId;
      if (stopId) navigateToStop(stopId);
      return;
    }

    // New stop card row click - highlight + navigate (skip if edit button was clicked)
    const cardRow = e.target.closest('.stop-card-row');
    if (cardRow && !e.target.closest('.stop-edit-icon')) {
      const stopId = cardRow.dataset.stopId;
      if (stopId) {
        _onCardClick(stopId);
        navigateToStop(stopId);
      }
      return;
    }

    // Back button on detail page - navigate to overview
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

    // Sidebar item click on detail page - navigate to that stop
    const sidebarItem = e.target.closest('.stops-sidebar-item');
    if (sidebarItem) {
      const stopId = sidebarItem.dataset.stopId;
      if (stopId) navigateToStop(stopId);
      return;
    }

    // Day CTA box in stop detail - navigate to day detail
    const dayCta = e.target.closest('.stop-day-cta');
    if (dayCta) {
      const dayNum = dayCta.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Day timeline header - toggle inline expand/collapse
    const dayTimelineHeader = e.target.closest('.day-timeline-header');
    if (dayTimelineHeader) {
      const dayNum = dayTimelineHeader.dataset.dayNum;
      if (dayNum) _toggleDayExpand(dayNum);
      return;
    }

    // Day overview card - navigate to day detail (legacy fallback)
    const dayCard = e.target.closest('.day-overview-card');
    if (dayCard) {
      const dayNum = dayCard.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Day detail back - days overview
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

    // Days sidebar item - navigate to that day
    const daySidebarItem = e.target.closest('.days-sidebar-item');
    if (daySidebarItem) {
      const dayNum = daySidebarItem.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

    // Day card v2 (overview grid) - drill down to day detail
    const dayCardV2 = e.target.closest('.day-card-v2');
    if (dayCardV2) {
      const dayNum = dayCardV2.dataset.dayNum;
      if (dayNum) navigateToDay(dayNum);
      return;
    }

  });
}

// ---------------------------------------------------------------------------
// Breadcrumb Delegation (separate from _initGuideDelegation — breadcrumb is outside #guide-content)
// ---------------------------------------------------------------------------

function _initBreadcrumbDelegation() {
  if (_breadcrumbDelegationReady) return;
  _breadcrumbDelegationReady = true;
  var bar = document.getElementById('guide-breadcrumb');
  if (!bar) return;
  bar.addEventListener('click', function(e) {
    var seg = e.target.closest('.guide-breadcrumb__segment');
    if (!seg || seg.classList.contains('guide-breadcrumb__segment--active')) return;
    var navLevel = seg.getAttribute('data-nav-level');
    var plan = S.result;
    if (!plan) return;
    if (navLevel === 'overview') {
      _activeStopId = null;
      _activeDayNum = null;
      _navigateToOverview();
    } else if (navLevel === 'day') {
      var dayNum = seg.getAttribute('data-day-num');
      _activeStopId = null;
      if (dayNum) navigateToDay(Number(dayNum));
    }
  });
}

// ---------------------------------------------------------------------------
// Overview Navigation Helper
// ---------------------------------------------------------------------------

function _navigateToOverview() {
  var plan = S.result;
  if (!plan) return;
  _activeDayNum = null;
  _activeStopId = null;
  _drillTransition(
    function() { return renderOverview(plan); },
    function() { _initGuideDelegation(); if (typeof _initOverviewInteractions === 'function') _initOverviewInteractions(plan); }
  );
  _renderBreadcrumb('overview', plan, null, null);
  _updateMapForTab(plan, 'overview', 'overview', {});
  if (plan._saved_travel_id) {
    var title = plan.custom_name || plan.title || '';
    Router.navigate(Router.travelPath(plan._saved_travel_id, title), { skipDispatch: true });
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
      btn.textContent = t('guide.save_first');
      setTimeout(() => { btn.textContent = orig; }, 3000);
    }
    return;
  }

  // Inline two-click confirmation
  if (btn && btn.dataset.confirmPending !== '1') {
    btn.dataset.confirmPending = '1';
    btn.textContent = t('travels.confirm_action');
    btn.classList.add('btn-warning');
    setTimeout(() => {
      if (btn && btn.dataset.confirmPending === '1') {
        btn.dataset.confirmPending = '';
        btn.textContent = t('guide.replan_btn');
        btn.classList.remove('btn-warning');
      }
    }, 3000);
    return;
  }

  if (btn) {
    btn.dataset.confirmPending = '';
    btn.disabled = true;
    btn.textContent = t('guide.starting');
    btn.classList.remove('btn-warning');
  }

  try {
    const { job_id } = await apiReplanTravel(savedId);
    S.jobId = job_id;
    showSection('progress');
    Router.navigate('/progress/' + job_id);
    document.getElementById('progress-error').style.display = 'none';
    const statusEl = document.getElementById('progress-agent-status');
    if (statusEl) statusEl.textContent = t('guide.recalculating');

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
        if (errEl) { errEl.textContent = t('guide.error_prefix') + ' ' + (data.error || t('guide.unknown_error')); errEl.style.display = ''; }
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
      btn.textContent = t('guide.error_retry');
      setTimeout(() => { if (btn) btn.textContent = t('guide.replan_btn'); }, 4000);
    }
    console.error('Replan-Fehler:', err);
  }
}
