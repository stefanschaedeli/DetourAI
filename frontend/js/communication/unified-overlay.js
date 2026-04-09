'use strict';

// Unified Overlay — loading overlay and SSE progress overlay combined into one consistent UI.
// Reads: t (i18n.js).
// Provides: showLoading, hideLoading, resetLoading, setLoadingProgress, updateLoadingLabel,
//           progressOverlay, overlayAddUpcoming, overlaySetProgress, overlayDebugPush, toggleDebugLog.

(function () {

  // ---------------------------------------------------------------------------
  // Internal state
  // ---------------------------------------------------------------------------

  let _pendingCount   = 0;          // reference counter (showLoading / hideLoading)
  let _mode           = null;       // 'simple' | 'sse' | null
  let _summary        = '';         // text shown in top summary zone
  let _progress       = null;       // null = indeterminate, 0-100 = determinate
  const _tasks        = new Map();  // key → {text, status, detail, el, iconEl, textEl, detailEl}
  let _debugOpen      = false;      // persisted to localStorage
  const _debugEntries = [];         // ring buffer, max 200 entries
  const _DEBUG_KEY    = 'tp_v1_debug_open';
  const _DEBUG_MAX    = 200;
  const _DEBUG_SHOW   = 50;         // number of entries rendered at once

  // ---------------------------------------------------------------------------
  // DOM refs (resolved lazily)
  // ---------------------------------------------------------------------------

  let _overlayEl     = null;
  let _summaryEl     = null;
  let _fillEl        = null;
  let _tasksEl       = null;
  let _debugToggleEl = null;
  let _debugLogEl    = null;

  function _ensureRefs() {
    if (!_overlayEl)     _overlayEl     = document.getElementById('unified-overlay');
    if (!_summaryEl)     _summaryEl     = document.getElementById('uo-summary');
    if (!_fillEl)        _fillEl        = document.getElementById('uo-progress-fill');
    if (!_tasksEl)       _tasksEl       = document.getElementById('uo-tasks');
    if (!_debugToggleEl) _debugToggleEl = document.getElementById('uo-debug-toggle');
    if (!_debugLogEl)    _debugLogEl    = document.getElementById('uo-debug-log');
  }

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------

  // Remove all children from an element using safe DOM methods.
  function _clearEl(el) {
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  // ---------------------------------------------------------------------------
  // Icon element factories
  // ---------------------------------------------------------------------------

  function _makeSpinner() {
    const el = document.createElement('div');
    el.className = 'uo-spinner';
    return el;
  }

  function _makeCheck() {
    const svg  = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'uo-check');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2.5');
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    poly.setAttribute('points', '20 6 9 17 4 12');
    svg.appendChild(poly);
    return svg;
  }

  function _makeDot() {
    const el = document.createElement('div');
    el.className = 'uo-dot';
    return el;
  }

  // Return a new icon element for the given status string.
  function _iconForStatus(status) {
    if (status === 'done')     return _makeCheck();
    if (status === 'upcoming') return _makeDot();
    return _makeSpinner();
  }

  // ---------------------------------------------------------------------------
  // Task DOM management
  // ---------------------------------------------------------------------------

  // Create a task row element, store it in _tasks, and return the row element.
  function _createTaskEl(key, text, status) {
    const rowEl    = document.createElement('div');
    rowEl.className = 'uo-task uo-task--' + status;

    const iconWrap = document.createElement('div');
    iconWrap.className = 'uo-task-icon';
    iconWrap.appendChild(_iconForStatus(status));

    const textEl   = document.createElement('span');
    textEl.className = 'uo-task-text';
    textEl.textContent = text;

    const detailEl = document.createElement('span');
    detailEl.className = 'uo-task-detail';

    rowEl.append(iconWrap, textEl, detailEl);

    _tasks.set(key, { text, status, detail: '', el: rowEl, iconEl: iconWrap, textEl, detailEl });
    return rowEl;
  }

  // Sync status classes and icon for an existing task entry (mutates DOM in place).
  // Skips icon rebuild when status has not changed since last apply.
  function _applyTaskStatus(entry) {
    const { el, iconEl, status } = entry;

    el.classList.remove('uo-task--active', 'uo-task--done', 'uo-task--upcoming');
    el.classList.add('uo-task--' + status);

    // Only rebuild the icon element when the status has actually changed.
    if (entry.appliedStatus !== status) {
      _clearEl(iconEl);
      iconEl.appendChild(_iconForStatus(status));
      entry.appliedStatus = status;
    }
  }

  // ---------------------------------------------------------------------------
  // Debug log rendering
  // ---------------------------------------------------------------------------

  function _renderDebugLog() {
    if (!_debugLogEl) return;
    // Clear existing entries safely.
    _clearEl(_debugLogEl);
    const slice = _debugEntries.slice(-_DEBUG_SHOW);
    for (const entry of slice) {
      const div      = document.createElement('div');
      const level    = (entry.level || 'info').toLowerCase();
      div.className  = 'uo-log-entry uo-log-' + level;

      const agentEl  = document.createElement('span');
      agentEl.className = 'uo-log-agent';
      agentEl.textContent = '[' + (entry.agent || '') + '] ';

      const msgNode  = document.createTextNode(entry.message || '');

      div.appendChild(agentEl);
      div.appendChild(msgNode);
      _debugLogEl.appendChild(div);
    }
    _debugLogEl.scrollTop = _debugLogEl.scrollHeight;
  }

  // ---------------------------------------------------------------------------
  // Main render function
  // ---------------------------------------------------------------------------

  function _render() {
    _ensureRefs();
    if (!_overlayEl) return;

    const visible = _pendingCount > 0 || _mode === 'sse';

    // Visibility
    _overlayEl.style.display = visible ? 'flex' : 'none';
    _overlayEl.setAttribute('aria-busy', visible ? 'true' : 'false');
    if (!visible) return;

    // Summary text
    if (_summaryEl) {
      _summaryEl.textContent = _summary || (typeof t === 'function' ? t('loading.default') : 'Laden…');
    }

    // Progress bar
    if (_fillEl) {
      if (_progress === null) {
        _fillEl.classList.add('uo-progress-indeterminate');
        _fillEl.style.width = '';
      } else {
        _fillEl.classList.remove('uo-progress-indeterminate');
        _fillEl.style.width = Math.min(100, Math.max(0, _progress)) + '%';
      }
    }

    // Task list
    if (_tasksEl) {
      if (_mode === 'sse') {
        _renderTasksSSE();
      } else {
        _renderTasksSimple();
      }
    }

    // Debug toggle button label
    if (_debugToggleEl) {
      _debugToggleEl.textContent = typeof t === 'function' ? t('overlay.debug_toggle') : 'Debug';
    }

    // Debug log visibility
    if (_debugLogEl) {
      _debugLogEl.style.display = _debugOpen ? 'block' : 'none';
      if (_debugOpen) _renderDebugLog();
    }
  }

  // Simple mode: only show the single active task line; detach all others.
  function _renderTasksSimple() {
    for (const [, entry] of _tasks) {
      if (entry.status === 'active') {
        if (!entry.el.parentNode) {
          _tasksEl.appendChild(entry.el);
        }
      } else {
        if (entry.el.parentNode) {
          entry.el.parentNode.removeChild(entry.el);
        }
      }
    }
  }

  // SSE mode: render done → active → upcoming groups in order.
  function _renderTasksSSE() {
    const done     = [];
    const active   = [];
    const upcoming = [];

    for (const [key, entry] of _tasks) {
      if (entry.status === 'done')         done.push(key);
      else if (entry.status === 'active')  active.push(key);
      else                                 upcoming.push(key);
    }

    const orderedKeys = [...done, ...active, ...upcoming];
    for (const key of orderedKeys) {
      const entry = _tasks.get(key);
      _applyTaskStatus(entry);
      // appendChild moves the element if it is already in the DOM.
      _tasksEl.appendChild(entry.el);
    }

    _tasksEl.scrollTop = _tasksEl.scrollHeight;
  }

  // ---------------------------------------------------------------------------
  // Initialisation
  // ---------------------------------------------------------------------------

  // Restore debug panel state from localStorage.
  try {
    _debugOpen = localStorage.getItem(_DEBUG_KEY) === 'true';
  } catch (_) {
    _debugOpen = false;
  }

  // Wire up the debug toggle button once the DOM is ready.
  document.addEventListener('DOMContentLoaded', function () {
    _ensureRefs();
    if (_debugToggleEl) {
      _debugToggleEl.addEventListener('click', function () { toggleDebugLog(); });
    }
  });

  // ---------------------------------------------------------------------------
  // Public API — backward-compatible globals from loading.js
  // ---------------------------------------------------------------------------

  /**
   * Show the loading overlay for a simple (non-SSE) operation.
   * Increments the pending reference counter.
   * SSE mode takes priority — if already in SSE mode the counter is still incremented
   * but the visual state is not changed to simple mode.
   */
  window.showLoading = function (message) {
    _pendingCount++;
    if (_mode !== 'sse') {
      _mode = 'simple';
      _summary = message || (typeof t === 'function' ? t('loading.default') : 'Laden…');

      // Replace all tasks with a single active line.
      _tasks.clear();
      if (_tasksEl) _clearEl(_tasksEl);
      _createTaskEl('simple', _summary, 'active');
    }
    _render();
  };

  /**
   * Decrement the pending counter (minimum 0).
   * Hides the overlay when the counter reaches zero and SSE mode is not active.
   */
  window.hideLoading = function () {
    _pendingCount = Math.max(0, _pendingCount - 1);
    if (_pendingCount === 0 && _mode === 'simple') {
      _mode = null;
    }
    _render();
  };

  /**
   * Force-reset the pending counter to zero.
   * Hides the overlay unless SSE mode is active.
   */
  window.resetLoading = function () {
    _pendingCount = 0;
    if (_mode === 'simple') _mode = null;
    _render();
  };

  /**
   * Set a determinate progress value (0-100) or null for indeterminate.
   * Applies to the visible progress bar regardless of mode.
   */
  window.setLoadingProgress = function (value) {
    _progress = value;
    _render();
  };

  /**
   * Update the summary label text without changing the pending counter.
   */
  window.updateLoadingLabel = function (message) {
    _summary = message || (typeof t === 'function' ? t('loading.default') : 'Laden…');
    if (_summaryEl) _summaryEl.textContent = _summary;
    const simpleTask = _tasks.get('simple');
    if (simpleTask) {
      simpleTask.text = _summary;
      simpleTask.textEl.textContent = _summary;
    }
  };

  // ---------------------------------------------------------------------------
  // Public API — backward-compatible globals from sse-overlay.js
  // ---------------------------------------------------------------------------

  /**
   * SSE-aware progress overlay — interface-compatible with the old progressOverlay object.
   */
  window.progressOverlay = {

    /**
     * Open the overlay in SSE mode for a new planning phase.
     * Clears all existing task lines and resets progress to indeterminate.
     */
    open: function (phase) {
      _mode = 'sse';
      _tasks.clear();
      if (_tasksEl) _clearEl(_tasksEl);
      _summary  = phase || (typeof t === 'function' ? t('loading.default') : 'Laden…');
      _progress = null;
      _render();
    },

    /**
     * Close SSE mode.
     * The overlay hides only if _pendingCount is also zero.
     */
    close: function () {
      _mode = null;
      _progress = null;
      _render();
    },

    /**
     * Add a task line with spinner (active status).
     * No-op if a task with the same key already exists.
     */
    addLine: function (key, text) {
      if (_tasks.has(key)) return;
      const el = _createTaskEl(key, text, 'active');
      if (_tasksEl && _mode === 'sse') {
        _tasksEl.appendChild(el);
        _tasksEl.scrollTop = _tasksEl.scrollHeight;
      }
    },

    /**
     * Mark a task as done (checkmark icon) and optionally append detail text.
     */
    completeLine: function (key, detail) {
      const entry = _tasks.get(key);
      if (!entry) return;
      entry.status = 'done';
      entry.detail = detail || '';
      if (detail) entry.detailEl.textContent = '— ' + detail;
      _applyTaskStatus(entry);
      // Re-render task order so done items move to the top of the list.
      if (_mode === 'sse' && _tasksEl) _renderTasksSSE();
    },

    /**
     * Update the overlay summary heading text.
     */
    updatePhase: function (text) {
      _summary = text || '';
      if (_summaryEl) _summaryEl.textContent = _summary;
    }
  };

  // ---------------------------------------------------------------------------
  // Public API — new globals
  // ---------------------------------------------------------------------------

  /**
   * Add a task with 'upcoming' status (dot icon, italic).
   * No-op if a task with the same key already exists.
   */
  window.overlayAddUpcoming = function (key, text) {
    if (_tasks.has(key)) return;
    const el = _createTaskEl(key, text, 'upcoming');
    if (_tasksEl && _mode === 'sse') {
      _tasksEl.appendChild(el);
    }
  };

  /**
   * Set a determinate progress percentage (0-100) on the progress bar.
   * Pass null to revert to indeterminate.
   */
  window.overlaySetProgress = function (pct) {
    _progress = pct;
    _render();
  };

  /**
   * Push a debug entry {level, agent, message, ts} into the ring buffer (max 200).
   * Re-renders the debug log panel immediately if it is currently open.
   */
  window.overlayDebugPush = function (entry) {
    _debugEntries.push(entry);
    if (_debugEntries.length > _DEBUG_MAX) {
      _debugEntries.shift();
    }
    if (_debugOpen && _debugLogEl) {
      _renderDebugLog();
    }
  };

  /**
   * Toggle the debug log panel open or closed.
   * Persists the choice to localStorage under key 'tp_v1_debug_open'.
   */
  window.toggleDebugLog = function () {
    _debugOpen = !_debugOpen;
    try {
      localStorage.setItem(_DEBUG_KEY, String(_debugOpen));
    } catch (_) {}
    _ensureRefs();
    if (_debugLogEl) {
      _debugLogEl.style.display = _debugOpen ? 'block' : 'none';
      if (_debugOpen) _renderDebugLog();
    }
  };

})();
