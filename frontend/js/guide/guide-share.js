// Guide Share — share toggle, link copy.
// Reads: S (state.js), esc() (state.js), _fetchQuiet (api.js).
// Provides: _renderShareToggle, _handleShareToggle, _copyShareLink
'use strict';

// ---------------------------------------------------------------------------
// Share toggle UI
// ---------------------------------------------------------------------------

/** Returns the HTML for the share toggle switch and, when active, the copy-link row. */
function _renderShareToggle(travelId, shareToken) {
  const checked = shareToken ? 'checked' : '';
  const shareUrl = shareToken
    ? `${location.origin}/travel/${travelId}?share=${encodeURIComponent(shareToken)}`
    : '';
  const urlSection = shareToken
    ? `<input type="text" class="share-url-input" value="${esc(shareUrl)}" readonly aria-label="${t('guide.share.url_input_label')}">
       <button class="btn btn-sm btn-secondary share-copy-btn" onclick="_copyShareLink(this, '${esc(shareUrl)}')">${esc(t('guide.share.copy_btn'))}</button>`
    : '';
  return `<div class="share-control" data-travel-id="${travelId}">
    <label class="toggle-switch">
      <input type="checkbox" ${checked} aria-label="${t('guide.share.toggle_label')}"
             onchange="_handleShareToggle(${travelId}, this.checked)">
      <span class="toggle-slider"></span>
    </label>
    <span class="share-label">${esc(t('guide.share.label'))}</span>
    ${urlSection}
  </div>`;
}

/** Enables or disables sharing for a travel, updating the share token and re-rendering the toggle. */
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
      showToast(t('guide.share.error'), 'error');
    }
  } else {
    // Confirm before revoking
    if (!await showConfirm(t('guide.share.disable_confirm'))) {
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
      showToast(t('guide.share.error'), 'error');
    }
  }
}

/** Copies the share URL to the clipboard and briefly shows a "Kopiert!" confirmation on the button. */
async function _copyShareLink(btn, url) {
  try {
    await navigator.clipboard.writeText(url);
    btn.textContent = t('guide.share.copied');
    setTimeout(() => { btn.textContent = t('guide.share.copy_btn'); }, 2000);
  } catch (err) {
    showToast(t('guide.share.copy_error'), 'error');
  }
}
