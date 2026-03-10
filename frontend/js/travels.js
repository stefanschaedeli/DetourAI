'use strict';

const _STAR_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;

function _renderStars(travelId, currentRating) {
  const stars = [1,2,3,4,5].map(n => {
    const filled = n <= currentRating;
    return `<span class="travel-star${filled ? ' active' : ''}" data-id="${travelId}" data-val="${n}" role="button" aria-label="${n} Stern${n !== 1 ? 'e' : ''}" tabindex="0">${_STAR_SVG}</span>`;
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
    console.error('Bewertung fehlgeschlagen:', err.message);
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
        console.error('Umbenennen fehlgeschlagen:', err.message);
      }
    }
  }

  input.addEventListener('blur', _commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentText; input.blur(); }
  });
}

function openTravelsDrawer() {
  document.getElementById('travels-drawer-overlay').classList.add('open');
  document.getElementById('travels-drawer').classList.add('open');
  document.body.style.overflow = 'hidden';
  loadTravelsList();
}

function closeTravelsDrawer() {
  document.getElementById('travels-drawer-overlay').classList.remove('open');
  document.getElementById('travels-drawer').classList.remove('open');
  document.body.style.overflow = '';
}

async function loadTravelsList() {
  const container = document.getElementById('travels-list');
  container.innerHTML = '<div class="travels-loading">Wird geladen…</div>';
  try {
    const { travels } = await apiGetTravels();
    if (!travels.length) {
      container.innerHTML = '<div class="travels-empty">Noch keine Reisen gespeichert.</div>';
      return;
    }
    container.innerHTML = travels.map(t => {
      const date = new Date(t.created_at).toLocaleDateString('de-CH',
        { day: '2-digit', month: '2-digit', year: 'numeric' });
      const cost = typeof t.total_cost_chf === 'number'
        ? `CHF ${t.total_cost_chf.toLocaleString('de-CH')}` : '–';
      const hasGuide = t.has_travel_guide ? '<span class="travel-card-badge">Reiseführer</span>' : '';
      const displayName = t.custom_name || t.title;
      const starsHtml = _renderStars(t.id, t.rating || 0);
      return `
        <div class="travel-card" data-id="${t.id}">
          <div class="travel-card-body">
            <div class="travel-card-title" data-id="${t.id}" data-title="${esc(t.title)}" data-current="${esc(displayName)}" title="Klicken zum Umbenennen">${esc(displayName)} ${hasGuide}</div>
            <div class="travel-card-rating">${starsHtml}</div>
            <div class="travel-card-meta">
              <span>${esc(date)}</span>
              <span>${t.num_stops} Stops · ${t.total_days} Tage</span>
              <span>${cost}</span>
            </div>
          </div>
          <div class="travel-card-actions">
            <button class="btn btn-sm btn-primary" onclick="openSavedTravel(${t.id})">Öffnen</button>
            <button class="btn btn-sm btn-secondary" onclick="replanSavedTravel(${t.id},this)" title="Reiseführer + stündliche Tagespläne neu generieren">Neu berechnen</button>
            <button class="btn btn-sm btn-danger" onclick="deleteSavedTravel(${t.id},this)">Löschen</button>
          </div>
        </div>`;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div class="travels-error">Fehler: ${esc(err.message)}</div>`;
  }
}

async function openSavedTravel(id) {
  showLoading('Reiseplan wird geladen…');
  try {
    const plan = await apiGetTravel(id);
    plan._saved_travel_id = id;   // track DB id for replan
    S.result = plan;
    S.jobId  = plan.job_id || null;
    lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
    closeTravelsDrawer();
    showTravelGuide(plan);
    showSection('travel-guide');
  } catch (err) {
    alert('Fehler beim Laden: ' + err.message);
  } finally {
    hideLoading();
  }
}

async function deleteSavedTravel(id, btn) {
  if (!confirm('Diese Reise wirklich löschen?')) return;
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
        if (c && !c.querySelector('.travel-card'))
          c.innerHTML = '<div class="travels-empty">Noch keine Reisen gespeichert.</div>';
      }, 200);
    }
  } catch (err) {
    alert('Fehler beim Löschen: ' + err.message);
    btn.disabled = false;
  }
}

async function replanSavedTravel(id, btn) {
  // Inline confirmation — avoids browser popup blocking
  if (btn.dataset.confirmPending !== '1') {
    btn.dataset.confirmPending = '1';
    btn.textContent = 'Bestätigen?';
    btn.classList.add('btn-warning');
    setTimeout(() => {
      if (btn.dataset.confirmPending === '1') {
        btn.dataset.confirmPending = '';
        btn.textContent = 'Neu berechnen';
        btn.classList.remove('btn-warning');
      }
    }, 3000);
    return;
  }

  // Confirmed — proceed
  btn.dataset.confirmPending = '';
  btn.disabled = true;
  btn.textContent = 'Wird gestartet…';
  btn.classList.remove('btn-warning');

  try {
    const { job_id } = await apiReplanTravel(id);
    closeTravelsDrawer();

    showSection('progress');
    document.getElementById('progress-error').style.display = 'none';
    const statusEl = document.getElementById('progress-agent-status');
    const timelineEl = document.getElementById('progress-timeline');
    if (statusEl)  statusEl.textContent = 'Reiseführer und Tagespläne werden neu berechnet…';
    if (timelineEl) timelineEl.innerHTML = '<div class="shimmer-line"></div><div class="shimmer-line short"></div>';
    S.jobId = job_id;

    _startReplanSSE(job_id, id);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Neu berechnen';
    // Show error inline in the card instead of alert
    const card = btn.closest('.travel-card');
    if (card) {
      const errDiv = document.createElement('div');
      errDiv.className = 'travel-card-error';
      errDiv.textContent = 'Fehler: ' + err.message;
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
      if (errEl) { errEl.textContent = 'Fehler: ' + (data.error || 'Unbekannter Fehler'); errEl.style.display = ''; }
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
