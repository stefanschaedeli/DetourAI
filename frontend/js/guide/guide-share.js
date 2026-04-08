// Guide Share — share toggle, link copy.
// Reads: S (state.js), esc() (state.js), _fetchQuiet (api.js).
// Provides: _renderShareToggle, _handleShareToggle, _copyShareLink
'use strict';

// ---------------------------------------------------------------------------
// Share toggle UI
// ---------------------------------------------------------------------------

function _renderShareToggle(travelId, shareToken) {
  const checked = shareToken ? 'checked' : '';
  const shareUrl = shareToken
    ? `${location.origin}/travel/${travelId}?share=${encodeURIComponent(shareToken)}`
    : '';
  const urlSection = shareToken
    ? `<input type="text" class="share-url-input" value="${esc(shareUrl)}" readonly aria-label="Teilbarer Link">
       <button class="btn btn-sm btn-secondary share-copy-btn" onclick="_copyShareLink(this, '${esc(shareUrl)}')">Link kopieren</button>`
    : '';
  return `<div class="share-control" data-travel-id="${travelId}">
    <label class="toggle-switch">
      <input type="checkbox" ${checked} aria-label="Teilen aktivieren"
             onchange="_handleShareToggle(${travelId}, this.checked)">
      <span class="toggle-slider"></span>
    </label>
    <span class="share-label">Teilen</span>
    ${urlSection}
  </div>`;
}

async function _handleShareToggle(travelId, checked) {
  const container = document.getElementById('share-toggle-container');
  const checkbox = container ? container.querySelector('input[type="checkbox"]') : null;

  if (checked) {
    // Enable sharing
    try {
      const result = await apiShareTravel(travelId);
      if (S.result) S.result.share_token = result.share_token;
      if (container) {
        container.textContent = '';
        const tmp = document.createElement('div');
        tmp.insertAdjacentHTML('afterbegin', _renderShareToggle(travelId, result.share_token));
        while (tmp.firstChild) container.appendChild(tmp.firstChild);
      }
    } catch (err) {
      // Revert toggle
      if (checkbox) checkbox.checked = false;
      alert('Teilen fehlgeschlagen. Bitte erneut versuchen.');
    }
  } else {
    // Confirm before revoking
    if (!confirm('Link deaktivieren? Bestehende Empfaenger verlieren Zugriff.')) {
      if (checkbox) checkbox.checked = true;
      return;
    }
    try {
      await apiUnshareTravel(travelId);
      if (S.result) S.result.share_token = null;
      if (container) {
        container.textContent = '';
        const tmp = document.createElement('div');
        tmp.insertAdjacentHTML('afterbegin', _renderShareToggle(travelId, null));
        while (tmp.firstChild) container.appendChild(tmp.firstChild);
      }
    } catch (err) {
      if (checkbox) checkbox.checked = true;
      alert('Teilen fehlgeschlagen. Bitte erneut versuchen.');
    }
  }
}

async function _copyShareLink(btn, url) {
  try {
    await navigator.clipboard.writeText(url);
    btn.textContent = 'Kopiert!';
    setTimeout(() => { btn.textContent = 'Link kopieren'; }, 2000);
  } catch (err) {
    alert('Link konnte nicht kopiert werden.');
  }
}
