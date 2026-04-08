'use strict';

(function () {
  let _pendingCount = 0;
  let _currentLabel = t('loading.default');
  let _overlay = null;
  let _labelEl = null;
  let _counterEl = null;
  let _fillEl = null;
  let _progress = null; // null = indeterminate, 0-100 = determinate

  function _ensureRefs() {
    if (!_overlay) _overlay   = document.getElementById('loading-overlay');
    if (!_labelEl) _labelEl   = document.getElementById('loading-label');
    if (!_counterEl) _counterEl = document.getElementById('loading-counter');
    if (!_fillEl) _fillEl     = document.querySelector('.loading-progress-fill');
  }

  function _render() {
    _ensureRefs();
    if (!_overlay) return;

    if (_pendingCount > 0) {
      _overlay.style.display = 'flex';
      _overlay.setAttribute('aria-busy', 'true');

      if (_labelEl) _labelEl.textContent = _currentLabel;

      if (_counterEl) {
        if (_pendingCount > 1) {
          _counterEl.style.display = 'block';
          _counterEl.textContent = t('loading.pending_requests', {count: _pendingCount});
        } else {
          _counterEl.style.display = 'none';
        }
      }

      if (_fillEl) {
        if (_progress === null) {
          _fillEl.style.width = '';
          _fillEl.classList.add('loading-progress-indeterminate');
        } else {
          _fillEl.classList.remove('loading-progress-indeterminate');
          _fillEl.style.width = `${Math.min(100, Math.max(0, _progress))}%`;
        }
      }
    } else {
      _overlay.style.display = 'none';
      _overlay.setAttribute('aria-busy', 'false');
    }
  }

  window.showLoading = function (message) {
    _currentLabel = message || t('loading.default');
    _pendingCount++;
    _render();
  };

  window.hideLoading = function () {
    _pendingCount = Math.max(0, _pendingCount - 1);
    _render();
  };

  window.resetLoading = function () {
    _pendingCount = 0;
    _render();
  };

  window.setLoadingProgress = function (value) {
    _progress = value;
    _render();
  };

  window.updateLoadingLabel = function (message) {
    _currentLabel = message || t('loading.default');
    if (_labelEl) _labelEl.textContent = _currentLabel;
  };
})();
