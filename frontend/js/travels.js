'use strict';

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
      return `
        <div class="travel-card" data-id="${t.id}">
          <div class="travel-card-body">
            <div class="travel-card-title">${esc(t.title)}</div>
            <div class="travel-card-meta">
              <span>${esc(date)}</span>
              <span>${t.num_stops} Stops · ${t.total_days} Tage</span>
              <span>${cost}</span>
            </div>
          </div>
          <div class="travel-card-actions">
            <button class="btn btn-sm btn-primary" onclick="openSavedTravel(${t.id})">Öffnen</button>
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

// Close on backdrop click
document.addEventListener('click', e => {
  if (e.target.id === 'travels-drawer-overlay') closeTravelsDrawer();
});
