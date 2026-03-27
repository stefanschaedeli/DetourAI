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
      footer.textContent = 'Erstellt mit DetourAI';
      content.appendChild(footer);
    }
  }

  // Pre-populate sidebar overlay content (D-03)
  if (typeof _populateSidebarOverlay === 'function' && !S.sharedMode) _populateSidebarOverlay();
}

function renderGuide(plan, tab) {
  activeTab = tab || 'overview';

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
          _lazyLoadCardImages(plan);
          _initScrollSync();
        });
      }
      break;
    case 'calendar':
      content.innerHTML = renderCalendar(plan);
      _initCalendarClicks(plan);
      break;
    case 'days':
      // Note: innerHTML usage is XSS-safe — all user content passed through esc()
      content.innerHTML = renderDaysOverview(plan);
      requestAnimationFrame(() => _initGuideDelegation());
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
  });
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
      btn.textContent = 'Zuerst in Meine Reisen speichern';
      setTimeout(() => { btn.textContent = orig; }, 3000);
    }
    return;
  }

  // Inline two-click confirmation
  if (btn && btn.dataset.confirmPending !== '1') {
    btn.dataset.confirmPending = '1';
    btn.textContent = 'Bestaetigen?';
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
    btn.textContent = 'Wird gestartet\u2026';
    btn.classList.remove('btn-warning');
  }

  try {
    const { job_id } = await apiReplanTravel(savedId);
    S.jobId = job_id;
    showSection('progress');
    Router.navigate('/progress/' + job_id);
    document.getElementById('progress-error').style.display = 'none';
    const statusEl = document.getElementById('progress-agent-status');
    if (statusEl) statusEl.textContent = 'Reisefuehrer und Tagesplaene werden neu berechnet\u2026';

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
      btn.textContent = 'Fehler \u2014 nochmals versuchen';
      setTimeout(() => { if (btn) btn.textContent = 'Neu berechnen'; }, 4000);
    }
    console.error('Replan-Fehler:', err);
  }
}
