'use strict';

// Travels — saved travels list: CRUD, star ratings, rename, and travel card rendering.
// Reads: S (state.js), Router (router.js), t (i18n.js), esc (core).
// Provides: loadTravelsList, openTravelsDrawer, closeTravelsDrawer, openSavedTravel, deleteSavedTravel, replanSavedTravel.

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const _STAR_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;

function _renderStars(travelId, currentRating) {
  const stars = [1,2,3,4,5].map(n => {
    const filled = n <= currentRating;
    return `<span class="travel-star${filled ? ' active' : ''}" data-id="${travelId}" data-val="${n}" role="button" aria-label="${n !== 1 ? t('travels.stars_aria', {stars: n}) : t('travels.star_aria', {stars: n})}" tabindex="0">${_STAR_SVG}</span>`;
  }).join('');
  return `<span class="travel-stars" data-id="${travelId}">${stars}</span>`;
}

async function _handleStarClick(starEl) {
  const id = parseInt(starEl.dataset.id, 10);
  const clickedVal = parseInt(starEl.dataset.val, 10);
  const container = starEl.closest('.travel-stars');
  const currentRating = container.querySelectorAll('.travel-star.active').length;
  const newRating = (clickedVal === currentRating) ? 0 : clickedVal;
  container.querySelectorAll('.travel-star').forEach(s => {
    const v = parseInt(s.dataset.val, 10);
    const active = v <= newRating;
    s.classList.toggle('active', active);
    // SVG content is static; only the active class drives fill color via CSS
  });
  try {
    await apiUpdateTravel(id, { rating: newRating });
  } catch (err) {
    console.error('Rating update failed:', err.message);
    loadTravelsList();
  }
}

function _startRename(titleEl) {
  const id = parseInt(titleEl.dataset.id, 10);
  const currentText = titleEl.dataset.current;
  const badge = titleEl.querySelector('.travel-card-badge');
  titleEl.innerHTML = '';
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentText;
  input.className = 'travel-card-rename-input';
  input.maxLength = 120;
  titleEl.appendChild(input);
  if (badge) titleEl.appendChild(badge);
  input.focus();
  input.select();

  async function _commit() {
    const newName = input.value.trim();
    const displayName = newName || titleEl.dataset.title;
    titleEl.innerHTML = esc(displayName) + (badge ? ' ' + badge.outerHTML : '');
    titleEl.dataset.current = displayName;
    if (newName !== currentText) {
      try {
        await apiUpdateTravel(id, { custom_name: newName || null });
      } catch (err) {
        titleEl.innerHTML = esc(currentText) + (badge ? ' ' + badge.outerHTML : '');
        titleEl.dataset.current = currentText;
        console.error('Rename failed:', err.message);
      }
    }
  }

  input.addEventListener('blur', _commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentText; input.blur(); }
  });
}

// ---------------------------------------------------------------------------
// Drawer control
// ---------------------------------------------------------------------------

/** Opens the saved-travels drawer and loads the list. */
function openTravelsDrawer() {
  document.getElementById('travels-drawer-overlay').classList.add('open');
  document.getElementById('travels-drawer').classList.add('open');
  document.body.style.overflow = 'hidden';
  if (location.pathname !== '/travels') {
    Router.navigate('/travels');
  }
  loadTravelsList();
}

/** Closes the saved-travels drawer and navigates back if on /travels. */
function closeTravelsDrawer() {
  document.getElementById('travels-drawer-overlay').classList.remove('open');
  document.getElementById('travels-drawer').classList.remove('open');
  document.body.style.overflow = '';
  // Navigate back if we came from /travels URL
  if (location.pathname === '/travels') {
    Router.navigate('/', { replace: true });
  }
}

// ---------------------------------------------------------------------------
// List rendering
// ---------------------------------------------------------------------------

/** Fetches and renders all saved travels as cards in the drawer. */
async function loadTravelsList() {
  const container = document.getElementById('travels-list');
  container.innerHTML = '<div class="travels-loading">' + esc(t('travels.loading')) + '</div>';
  try {
    const { travels } = await apiGetTravels();
    if (!travels.length) {
      container.innerHTML = '<div class="travels-empty">' + esc(t('travels.no_travels')) + '</div>';
      return;
    }
    container.innerHTML = travels.map(travel => {
      const date = new Date(travel.created_at).toLocaleDateString('de-CH',
        { day: '2-digit', month: '2-digit', year: 'numeric' });
      const cost = typeof travel.total_cost_chf === 'number'
        ? `CHF ${travel.total_cost_chf.toLocaleString('de-CH')}` : '–';
      const hasGuide = travel.has_travel_guide ? '<span class="travel-card-badge">' + esc(t('travels.guide_badge')) + '</span>' : '';
      const displayName = travel.custom_name || travel.title;
      const starsHtml = _renderStars(travel.id, travel.rating || 0);
      return `
        <div class="travel-card" data-id="${travel.id}">
          <div class="travel-card-body">
            <div class="travel-card-title" data-id="${travel.id}" data-title="${esc(travel.title)}" data-current="${esc(displayName)}" title="${esc(t('travels.rename_title'))}">${esc(displayName)} ${hasGuide}</div>
            <div class="travel-card-rating">${starsHtml}</div>
            <div class="travel-card-meta">
              <span>${esc(date)}</span>
              <span>${esc(t('travels.stops_days', {stops: travel.num_stops, days: travel.total_days}))}</span>
              <span>${cost}</span>
            </div>
          </div>
          <div class="travel-card-actions">
            <button class="btn btn-sm btn-primary" onclick="openSavedTravel(${travel.id})">${esc(t('travels.open_btn'))}</button>
            <button class="btn btn-sm btn-secondary" onclick="replanSavedTravel(${travel.id},this)" title="${esc(t('travels.replan_title'))}">${esc(t('travels.replan_btn'))}</button>
            <button class="btn btn-sm btn-danger" onclick="deleteSavedTravel(${travel.id},this)">${esc(t('travels.delete_btn'))}</button>
          </div>
        </div>`;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div class="travels-error">${esc(t('travels.error_prefix'))} ${esc(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// CRUD actions
// ---------------------------------------------------------------------------

/** Loads a saved travel by ID and opens the travel guide view. */
async function openSavedTravel(id) {
  showLoading(t('travels.loading_trip'));
  try {
    const plan = await apiGetTravel(id);
    plan._saved_travel_id = id;   // track DB id for replan
    S.result = plan;
    S.jobId  = plan.job_id || null;
    lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
    closeTravelsDrawer();
    const title = plan.custom_name || plan.title || '';
    showTravelGuide(plan);
    showSection('travel-guide');
    Router.navigate(Router.travelPath(id, title));
  } catch (err) {
    showToast(t('travels.load_error') + ' ' + err.message, 'error');
  } finally {
    hideLoading();
  }
}

/** Deletes a saved travel after confirmation and removes its card from the list. */
async function deleteSavedTravel(id, btn) {
  if (!await showConfirm(t('travels.confirm_delete'))) return;
  btn.disabled = true;
  try {
    await apiDeleteTravel(id);
    const card = document.querySelector(`.travel-card[data-id="${id}"]`);
    if (card) {
      card.style.transition = 'opacity .2s, transform .2s';
      card.style.opacity = '0';
      card.style.transform = 'translateX(20px)';
      setTimeout(() => {
        card.remove();
        const c = document.getElementById('travels-list');
        if (c && !c.querySelector('.travel-card')) {
          c.textContent = '';
          const emptyDiv = document.createElement('div');
          emptyDiv.className = 'travels-empty';
          emptyDiv.textContent = t('travels.no_travels');
          c.appendChild(emptyDiv);
        }
      }, 200);
    }
  } catch (err) {
    showToast(t('travels.delete_error') + ' ' + err.message, 'error');
    btn.disabled = false;
  }
}

/** Triggers a replan of a saved travel with inline two-step confirmation, then streams the result via SSE. */
async function replanSavedTravel(id, btn) {
  // Inline confirmation — avoids browser popup blocking
  if (btn.dataset.confirmPending !== '1') {
    btn.dataset.confirmPending = '1';
    btn.textContent = t('travels.confirm_action');
    btn.classList.add('btn-warning');
    setTimeout(() => {
      if (btn.dataset.confirmPending === '1') {
        btn.dataset.confirmPending = '';
        btn.textContent = t('travels.replan_btn');
        btn.classList.remove('btn-warning');
      }
    }, 3000);
    return;
  }

  // Confirmed — proceed
  btn.dataset.confirmPending = '';
  btn.disabled = true;
  btn.textContent = t('travels.starting');
  btn.classList.remove('btn-warning');

  try {
    const { job_id } = await apiReplanTravel(id);
    closeTravelsDrawer();

    showSection('progress');
    Router.navigate('/progress/' + job_id);
    document.getElementById('progress-error').style.display = 'none';
    const statusEl = document.getElementById('progress-agent-status');
    const timelineEl = document.getElementById('progress-timeline');
    if (statusEl)  statusEl.textContent = t('travels.recalculating');
    if (timelineEl) timelineEl.innerHTML = '<div class="shimmer-line"></div><div class="shimmer-line short"></div>';
    S.jobId = job_id;

    _startReplanSSE(job_id, id);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = t('travels.replan_btn');
    // Show error inline in the card instead of alert
    const card = btn.closest('.travel-card');
    if (card) {
      const errDiv = document.createElement('div');
      errDiv.className = 'travel-card-error';
      errDiv.textContent = t('travels.error_prefix') + ' ' + err.message;
      card.appendChild(errDiv);
      setTimeout(() => errDiv.remove(), 5000);
    }
  }
}

function _startReplanSSE(jobId, sourceTravelId) {
  const statusEl = document.getElementById('progress-agent-status');

  const source = openSSE(jobId, {
    job_complete: async (data) => {
      source.close();
      const plan = data;
      S.result = plan;
      S.jobId  = plan.job_id || jobId;
      lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
      showTravelGuide(plan);
      showSection('travel-guide');
    },
    job_error: (data) => {
      source.close();
      const errEl = document.getElementById('progress-error');
      if (errEl) { errEl.textContent = t('travels.error_prefix') + ' ' + (data.error || t('progress.unknown_error')); errEl.style.display = ''; }
    },
    debug_log: (data) => {
      if (statusEl && data.message) statusEl.textContent = data.message;
      if (typeof appendProgressLine === 'function') appendProgressLine(data);
    },
    stop_done: (data) => {
      if (typeof onStopDone === 'function') onStopDone(data);
    },
  });
}

// Star + rename delegation
document.getElementById('travels-list').addEventListener('click', e => {
  const star = e.target.closest('.travel-star');
  if (star) { _handleStarClick(star); return; }
  const titleEl = e.target.closest('.travel-card-title');
  if (titleEl && !titleEl.querySelector('input')) { _startRename(titleEl); }
});

// Close on backdrop click
document.addEventListener('click', e => {
  if (e.target.id === 'travels-drawer-overlay') closeTravelsDrawer();
});
