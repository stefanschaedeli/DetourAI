'use strict';

// SSE Overlay — phase spinner/check lines shown during the AI planning pipeline.
// Reads: t (i18n.js).
// Provides: progressOverlay.open, progressOverlay.close, progressOverlay.addLine,
//           progressOverlay.completeLine, progressOverlay.updatePhase.

const progressOverlay = (() => {
  // ---------------------------------------------------------------------------
  // Icons and DOM refs
  // ---------------------------------------------------------------------------
  const ICON_SPINNER = `<div class="spo-spinner"></div>`;
  const ICON_CHECK   = `<svg class="spo-check" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;

  let _overlayEl = null, _phaseEl = null, _linesEl = null;
  const _lines = new Map();

  function _ensureRefs() {
    if (!_overlayEl) _overlayEl = document.getElementById('sse-progress-overlay');
    if (!_phaseEl)  _phaseEl   = document.getElementById('spo-phase');
    if (!_linesEl)  _linesEl   = document.getElementById('spo-lines');
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /** Show the overlay, clear previous lines, and set the phase heading text. */
  function open(phase) {
    _ensureRefs();
    _lines.clear();
    if (_linesEl)  _linesEl.innerHTML = '';
    if (_phaseEl)  _phaseEl.textContent = phase || t('loading.default');
    if (_overlayEl) _overlayEl.style.display = 'flex';
  }

  /** Hide the overlay. */
  function close() {
    _ensureRefs();
    if (_overlayEl) _overlayEl.style.display = 'none';
  }

  /** Add a new spinner line with the given key and label text (no-op if key already exists). */
  function addLine(key, text) {
    _ensureRefs();
    if (!_linesEl || _lines.has(key)) return;
    const lineEl   = document.createElement('div');
    lineEl.className = 'spo-line';
    const iconEl   = document.createElement('div');
    iconEl.className = 'spo-line-icon';
    iconEl.innerHTML = ICON_SPINNER;
    const textEl   = document.createElement('span');
    textEl.className = 'spo-line-text';
    textEl.textContent = text;
    const detailEl = document.createElement('span');
    detailEl.className = 'spo-line-detail';
    lineEl.append(iconEl, textEl, detailEl);
    _linesEl.appendChild(lineEl);
    _linesEl.scrollTop = _linesEl.scrollHeight;
    _lines.set(key, { el: lineEl, iconEl, textEl, detailEl });
  }

  /** Replace the spinner on a line with a checkmark and optionally append detail text. */
  function completeLine(key, detail) {
    const refs = _lines.get(key);
    if (!refs) return;
    refs.iconEl.innerHTML = ICON_CHECK;
    refs.el.classList.add('done');
    if (detail) refs.detailEl.textContent = '— ' + detail;
  }

  /** Update the phase heading text without resetting the lines. */
  function updatePhase(text) {
    _ensureRefs();
    if (_phaseEl) _phaseEl.textContent = text || '';
  }

  return { open, close, addLine, completeLine, updatePhase };
})();
