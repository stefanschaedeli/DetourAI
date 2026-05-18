// Log Viewer — admin-only live log tail with source/level/job/search filters and download.
// Reads: S (state.js), _fetchWithAuth (api.js), authGetToken (auth.js), t (i18n.js),
//        Router.navigate (router.js), showSection (index.html).
// Provides: showLogViewer, closeLogViewer.

'use strict';

// ---------------------------------------------------------------------------
// Module state (never written to S — admin-only, ephemeral)
// ---------------------------------------------------------------------------

let _sse = null;
let _liveMode = true;
let _autoScroll = true;
let _lineCount = 0;
const _MAX_LINES = 5000;
const _DROP_BATCH = 500;

let _sources = new Set(['agents', 'orchestrator', 'api', 'frontend']);
let _levels  = new Set();
let _specificFile = '';
let _jobId   = '';
let _search  = '';

// ---------------------------------------------------------------------------
// DOM references (set during init)
// ---------------------------------------------------------------------------

let _pane        = null;
let _statusPill  = null;
let _newBtn      = null;
let _fileSelect  = null;
let _jobInput    = null;
let _searchInput = null;
let _liveCheckbox = null;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Entry point — called by router when navigating to /admin/logs. */
function showLogViewer() {
  showSection('logs-section');
  _init();
}

/** Tear down SSE connection when navigating away. */
function closeLogViewer() {
  _closeSse();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function _init() {
  _pane         = document.getElementById('logs-pane');
  _statusPill   = document.getElementById('logs-status-pill');
  _newBtn       = document.getElementById('logs-new-indicator');
  _fileSelect   = document.getElementById('logs-file-select');
  _jobInput     = document.getElementById('logs-job-input');
  _searchInput  = document.getElementById('logs-search-input');
  _liveCheckbox = document.getElementById('logs-live-checkbox');

  if (!_pane) return;

  _resetState();
  _attachListeners();
  _fetchFiles();
  _openStream();
}

function _resetState() {
  _liveMode    = true;
  _autoScroll  = true;
  _lineCount   = 0;
  _sources     = new Set(['agents', 'orchestrator', 'api', 'frontend']);
  _levels      = new Set();
  _specificFile = '';
  _jobId       = '';
  _search      = '';
  if (_pane) _pane.textContent = '';
  if (_liveCheckbox) _liveCheckbox.checked = true;
  if (_newBtn) _newBtn.classList.remove('visible');
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

function _attachListeners() {
  document.querySelectorAll('.logs-source-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const src = chip.dataset.source;
      if (_sources.has(src)) {
        if (_sources.size > 1) _sources.delete(src);
      } else {
        _sources.add(src);
      }
      chip.classList.toggle('active', _sources.has(src));
      _specificFile = '';
      if (_fileSelect) _fileSelect.value = '';
      _reopenStream();
    });
  });

  document.querySelectorAll('.logs-level-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const lvl = chip.dataset.level;
      if (_levels.has(lvl)) _levels.delete(lvl);
      else _levels.add(lvl);
      chip.classList.toggle('active', _levels.has(lvl));
      _reopenStream();
    });
  });

  if (_fileSelect) {
    _fileSelect.addEventListener('change', () => {
      _specificFile = _fileSelect.value;
      _reopenStream();
    });
  }

  if (_jobInput) {
    _jobInput.addEventListener('input', _debounce(() => {
      _jobId = _jobInput.value.trim();
      _reopenStream();
    }, 300));
  }
  if (_searchInput) {
    _searchInput.addEventListener('input', _debounce(() => {
      _search = _searchInput.value.trim();
      _reopenStream();
    }, 300));
  }

  if (_liveCheckbox) {
    _liveCheckbox.addEventListener('change', () => {
      _liveMode = _liveCheckbox.checked;
      if (_liveMode) _reopenStream();
      else _closeSse();
    });
  }

  const dlBtn = document.getElementById('logs-download-btn');
  if (dlBtn) dlBtn.addEventListener('click', _download);

  if (_newBtn) {
    _newBtn.addEventListener('click', () => {
      _autoScroll = true;
      _newBtn.classList.remove('visible');
      _pane.scrollTop = _pane.scrollHeight;
    });
  }

  if (_pane) {
    _pane.addEventListener('scroll', () => {
      const atBottom = _pane.scrollHeight - _pane.scrollTop - _pane.clientHeight < 60;
      if (atBottom) {
        _autoScroll = true;
        if (_newBtn) _newBtn.classList.remove('visible');
      } else {
        _autoScroll = false;
      }
    });
  }

  document.getElementById('logs-retry-btn')?.addEventListener('click', _reopenStream);
}

// ---------------------------------------------------------------------------
// File tree
// ---------------------------------------------------------------------------

async function _fetchFiles() {
  if (!_fileSelect) return;
  try {
    const res = await _fetchWithAuth('/api/admin/logs/files');
    if (!res.ok) return;
    const data = await res.json();
    while (_fileSelect.options.length > 1) _fileSelect.remove(1);
    for (const group of data.groups || []) {
      for (const file of group.files || []) {
        const opt = document.createElement('option');
        opt.value = file.path;
        opt.textContent = file.path;
        _fileSelect.appendChild(opt);
        for (const rot of file.rotations || []) {
          const ropt = document.createElement('option');
          ropt.value = rot.path;
          ropt.textContent = '  ↳ ' + rot.path.split('/').pop();
          _fileSelect.appendChild(ropt);
        }
      }
    }
  } catch (_) {}
}

// ---------------------------------------------------------------------------
// SSE stream
// ---------------------------------------------------------------------------

function _buildStreamUrl() {
  const params = new URLSearchParams();
  const token = authGetToken();
  if (token) params.set('token', token);
  params.set('initial_lines', '500');
  if (_specificFile) {
    params.set('sources', _specificFile);
  } else {
    params.set('sources', [..._sources].join(','));
  }
  if (_levels.size) params.set('levels', [..._levels].join(','));
  if (_jobId) params.set('job_id', _jobId);
  if (_search) params.set('search', _search);
  return '/api/admin/logs/stream?' + params.toString();
}

function _openStream() {
  if (!_liveMode) return;
  _closeSse();
  _setStatus('live');

  _sse = new EventSource(_buildStreamUrl());

  _sse.addEventListener('log', (e) => {
    let entry;
    try { entry = JSON.parse(e.data); } catch (_) { return; }
    _appendLine(entry);
  });

  _sse.addEventListener('ping', () => {});

  _sse.onerror = () => {
    _setStatus('error');
    _closeSse();
  };
}

function _reopenStream() {
  if (_pane) _pane.textContent = '';
  _lineCount = 0;
  _autoScroll = true;
  if (_newBtn) _newBtn.classList.remove('visible');
  _openStream();
}

function _closeSse() {
  if (_sse) { _sse.close(); _sse = null; }
  _setStatus('paused');
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function _appendLine(entry) {
  if (!_pane) return;

  if (_lineCount >= _MAX_LINES) {
    const toRemove = _pane.querySelectorAll('.log-line');
    for (let i = 0; i < _DROP_BATCH && i < toRemove.length; i++) {
      toRemove[i].remove();
    }
    _lineCount -= Math.min(_DROP_BATCH, _lineCount);
  }

  const line = document.createElement('div');
  line.className = 'log-line log-level-' + (entry.level || 'RAW');

  if (entry.ts) {
    const ts = document.createElement('span');
    ts.className = 'log-ts';
    ts.textContent = entry.ts;
    line.appendChild(ts);
  }

  const badge = document.createElement('span');
  badge.className = 'log-level-badge';
  badge.textContent = entry.level || 'RAW';
  line.appendChild(badge);

  if (entry.agent) {
    const agent = document.createElement('span');
    agent.className = 'log-agent';
    agent.textContent = entry.agent;
    line.appendChild(agent);
  }

  if (entry.job) {
    const job = document.createElement('span');
    job.className = 'log-job-chip';
    job.textContent = 'job:' + entry.job;
    line.appendChild(job);
  }

  const msg = document.createElement('span');
  msg.className = 'log-message';
  msg.textContent = entry.message || '';
  line.appendChild(msg);

  _pane.appendChild(line);
  _lineCount++;

  if (_autoScroll) {
    _pane.scrollTop = _pane.scrollHeight;
  } else if (_newBtn) {
    _newBtn.classList.add('visible');
    _newBtn.textContent = '↓ ' + t('logs.new_logs_btn');
  }
}

// ---------------------------------------------------------------------------
// Status pill
// ---------------------------------------------------------------------------

function _setStatus(state) {
  if (!_statusPill) return;
  _statusPill.className = 'logs-status-pill ' + state;
  const labels = { live: t('logs.status_live'), paused: t('logs.status_paused'), error: t('logs.status_disconnected') };
  const dot = document.createElement('span');
  dot.className = 'status-dot';
  _statusPill.textContent = '';
  _statusPill.appendChild(dot);
  _statusPill.appendChild(document.createTextNode(' ' + (labels[state] || state)));
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

function _download() {
  if (!_pane) return;
  const lines = [..._pane.querySelectorAll('.log-line')].map(el => el.textContent);
  const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const now = new Date();
  const stamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = url;
  a.download = 'detourai-logs-' + stamp + '.txt';
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function _debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
