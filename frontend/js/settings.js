'use strict';

/* ── Settings Page ── */

const AGENT_META = {
  'route_architect':            { label: 'Route Architect',            role: 'Routenplanung' },
  'stop_options_finder':        { label: 'Stop Options Finder',        role: 'Stopp-Vorschläge' },
  'region_planner':             { label: 'Region Planner',             role: 'Regionen-Planung' },
  'accommodation_researcher':   { label: 'Accommodation Researcher',   role: 'Unterkünfte' },
  'activities':                 { label: 'Activities Agent',           role: 'Aktivitäten' },
  'restaurants':                { label: 'Restaurants Agent',          role: 'Restaurants' },
  'day_planner':                { label: 'Day Planner',                role: 'Tagesplanung' },
  'travel_guide':               { label: 'Travel Guide',               role: 'Reiseführer' },
  'trip_analysis':              { label: 'Trip Analysis',               role: 'Reise-Analyse' },
};

const MODEL_OPTIONS = [
  { value: 'claude-opus-4-5',   label: 'Claude Opus' },
  { value: 'claude-sonnet-4-5', label: 'Claude Sonnet' },
  { value: 'claude-haiku-4-5',  label: 'Claude Haiku' },
];

let _settingsData = null;
let _saveTimer = null;
let _previousSection = 'form-section';

function openSettingsPage() {
  // Remember which section was active
  document.querySelectorAll('.section').forEach(s => {
    if (s.classList.contains('active') && s.id !== 'settings-section') {
      _previousSection = s.id;
    }
    s.classList.remove('active');
  });
  document.getElementById('settings-section').classList.add('active');
  loadSettings();
}

function closeSettingsPage() {
  document.getElementById('settings-section').classList.remove('active');
  const prev = document.getElementById(_previousSection);
  if (prev) prev.classList.add('active');
}

async function loadSettings() {
  try {
    _settingsData = await apiGetSettings();
    renderSettingsPage();
  } catch (err) {
    console.error('Settings laden fehlgeschlagen:', err);
    apiLogError('error', `Settings laden: ${err.message}`, 'settings.js');
  }
}

function renderSettingsPage() {
  const container = document.getElementById('settings-section');
  const { settings, defaults, api_keys } = _settingsData;

  container.innerHTML = `
    <div class="settings-page">
      <div class="settings-header">
        <button class="settings-back-btn" onclick="closeSettingsPage()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Zurück
        </button>
        <h2>Einstellungen</h2>
      </div>

      ${_renderCategory('KI-Agenten', 'agent', _renderAgentCards(settings, defaults))}
      ${_renderCategory('Budget-Standardwerte', 'budget', _renderBudgetSection(settings, defaults))}
      ${_renderCategory('API & Performance', 'api', _renderApiSection(settings, defaults))}
      ${_renderCategory('System', 'system', _renderSystemSection(settings, defaults, api_keys))}
    </div>
    <div class="settings-toast" id="settings-toast">Gespeichert</div>
  `;
}

function _renderCategory(title, section, content) {
  return `
    <div class="settings-category" id="cat-${section}">
      <div class="settings-category-header" onclick="toggleSettingsCategory('${section}')">
        <h3>${esc(title)}</h3>
        <div class="settings-category-actions">
          <button class="settings-reset-btn" onclick="event.stopPropagation(); resetSettingsSection('${section}')" title="Auf Standard zurücksetzen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M1 4v6h6M23 20v-6h-6"/>
              <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
            </svg>
          </button>
          <svg class="settings-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
            <path d="M6 9l6 6 6-6"/>
          </svg>
        </div>
      </div>
      <div class="settings-category-body open">
        ${content}
      </div>
    </div>
  `;
}

function toggleSettingsCategory(section) {
  const body = document.querySelector(`#cat-${section} .settings-category-body`);
  body.classList.toggle('open');
  const chevron = document.querySelector(`#cat-${section} .settings-chevron`);
  chevron.classList.toggle('rotated');
}

function _renderAgentCards(settings, defaults) {
  return Object.entries(AGENT_META).map(([key, meta]) => {
    const modelKey = `agent.${key}.model`;
    const tokensKey = `agent.${key}.max_tokens`;
    const currentModel = settings[modelKey] || defaults[modelKey];
    const currentTokens = settings[tokensKey] || defaults[tokensKey];
    const isDefault = currentModel === defaults[modelKey] && currentTokens === defaults[tokensKey];

    return `
      <div class="settings-agent-card">
        <div class="settings-agent-header" onclick="toggleAgentCard(this)">
          <div class="settings-agent-info">
            <span class="settings-agent-name">${esc(meta.label)}</span>
            <span class="settings-badge">${esc(meta.role)}</span>
          </div>
          <div class="settings-agent-model-badge ${_modelClass(currentModel)}">
            ${esc(_modelLabel(currentModel))}
          </div>
        </div>
        <div class="settings-agent-body">
          <div class="settings-row">
            <label>Modell</label>
            <select onchange="saveSetting('${modelKey}', this.value)">
              ${MODEL_OPTIONS.map(m => `<option value="${m.value}" ${m.value === currentModel ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}
            </select>
          </div>
          <div class="settings-row">
            <label>Max Tokens</label>
            <div class="settings-slider-group">
              <input type="range" min="512" max="8192" step="256" value="${currentTokens}"
                oninput="this.nextElementSibling.textContent = this.value; debounceSave('${tokensKey}', Number(this.value))">
              <span class="settings-slider-value">${currentTokens}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function toggleAgentCard(header) {
  header.parentElement.classList.toggle('expanded');
}

function _renderBudgetSection(settings, defaults) {
  return `
    ${_row('Unterkunftsanteil', _slider('budget.accommodation_pct', settings, 5, 80, 1, '%'))}
    ${_row('Fallback Unterkunft', _numberInput('budget.fallback_accommodation_chf', settings, 10, 500, 'CHF/Nacht'))}
    ${_row('Fallback Aktivitäten', _numberInput('budget.fallback_activities_chf', settings, 10, 300, 'CHF/Stop'))}
    ${_row('Fallback Verpflegung', _numberInput('budget.fallback_food_chf', settings, 10, 200, 'CHF/Nacht'))}
    ${_row('Treibstoff', _numberInput('budget.fuel_chf_per_hour', settings, 5, 50, 'CHF/Stunde'))}
    ${_row('Unterkunft-Multiplikator Min', _numberInput('budget.acc_multiplier_min', settings, 0.5, 2.0, '', 0.05))}
    ${_row('Unterkunft-Multiplikator Max', _numberInput('budget.acc_multiplier_max', settings, 0.5, 2.0, '', 0.05))}
  `;
}

function _renderApiSection(settings, defaults) {
  return `
    ${_row('Nominatim Verzögerung', _numberInput('api.nominatim_delay_ms', settings, 100, 2000, 'ms'))}
    ${_row('Nominatim Timeout', _numberInput('api.nominatim_timeout_s', settings, 1, 30, 's'))}
    ${_row('OSRM Timeout', _numberInput('api.osrm_timeout_s', settings, 1, 30, 's'))}
    ${_row('Wikipedia Timeout', _numberInput('api.wikipedia_timeout_s', settings, 1, 30, 's'))}
    ${_warningRow('Max Wiederholungen', _numberInput('api.retry_max_attempts', settings, 1, 10, ''))}
    ${_row('Parallele Unterkunftssuche', _numberInput('api.accommodation_parallelism', settings, 1, 5, ''))}
  `;
}

function _renderSystemSection(settings, defaults, apiKeys) {
  const testMode = settings['system.test_mode'];
  return `
    <div class="settings-row">
      <label>Test-Modus</label>
      <div class="settings-toggle-wrapper">
        <label class="settings-toggle">
          <input type="checkbox" ${testMode ? 'checked' : ''}
            onchange="saveSetting('system.test_mode', this.checked)">
          <span class="settings-toggle-slider"></span>
        </label>
        <span class="settings-toggle-label">${testMode ? 'An' : 'Aus'}</span>
      </div>
    </div>
    <div class="settings-row">
      <label>API-Key Status</label>
      <div class="settings-api-keys">
        <span class="settings-badge ${apiKeys.anthropic ? 'badge-ok' : 'badge-err'}">Anthropic ${apiKeys.anthropic ? '✓' : '✗'}</span>
        <span class="settings-badge ${apiKeys.google_maps ? 'badge-ok' : 'badge-err'}">Google Maps ${apiKeys.google_maps ? '✓' : '✗'}</span>
        <span class="settings-badge ${apiKeys.brave ? 'badge-ok' : 'badge-err'}">Brave ${apiKeys.brave ? '✓' : '✗'}</span>
      </div>
    </div>
    ${_row('Korridor-Puffer', _numberInput('geo.corridor_buffer_km', settings, 10, 100, 'km'))}
    ${_row('Log-Aufbewahrung', _numberInput('system.log_retention_days', settings, 1, 365, 'Tage'))}
    ${_warningRow('Redis Job-TTL', _numberInput('system.redis_job_ttl_s', settings, 3600, 604800, 's'))}
  `;
}

/* ── Helpers ── */

function _row(label, control) {
  return `<div class="settings-row"><label>${esc(label)}</label>${control}</div>`;
}

function _warningRow(label, control) {
  return `<div class="settings-row settings-warning"><label>${esc(label)}</label>${control}</div>`;
}

function _slider(key, settings, min, max, step, suffix) {
  const val = settings[key];
  return `
    <div class="settings-slider-group">
      <input type="range" min="${min}" max="${max}" step="${step}" value="${val}"
        oninput="this.nextElementSibling.textContent = this.value + '${suffix}'; debounceSave('${key}', Number(this.value))">
      <span class="settings-slider-value">${val}${suffix}</span>
    </div>
  `;
}

function _numberInput(key, settings, min, max, suffix, step) {
  const val = settings[key];
  const stepAttr = step ? `step="${step}"` : (Number.isInteger(val) ? 'step="1"' : 'step="0.05"');
  return `
    <div class="settings-input-group">
      <input type="number" min="${min}" max="${max}" ${stepAttr} value="${val}"
        onchange="debounceSave('${key}', Number(this.value))">
      ${suffix ? `<span class="settings-input-suffix">${esc(suffix)}</span>` : ''}
    </div>
  `;
}

function _modelClass(model) {
  if (model.includes('opus')) return 'model-opus';
  if (model.includes('sonnet')) return 'model-sonnet';
  return 'model-haiku';
}

function _modelLabel(model) {
  if (model.includes('opus')) return 'Opus';
  if (model.includes('sonnet')) return 'Sonnet';
  return 'Haiku';
}

/* ── Save Logic ── */

function debounceSave(key, value) {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => saveSetting(key, value), 500);
}

async function saveSetting(key, value) {
  try {
    await apiSaveSettings({ [key]: value });
    // Update local cache
    if (_settingsData) _settingsData.settings[key] = value;
    // Update toggle label if test mode
    if (key === 'system.test_mode') {
      const label = document.querySelector('.settings-toggle-label');
      if (label) label.textContent = value ? 'An' : 'Aus';
    }
    showSettingsToast();
  } catch (err) {
    console.error('Setting speichern fehlgeschlagen:', err);
    apiLogError('error', `Setting speichern: ${err.message}`, 'settings.js');
  }
}

function showSettingsToast() {
  const toast = document.getElementById('settings-toast');
  if (!toast) return;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 1500);
}

async function resetSettingsSection(section) {
  if (!confirm(`Alle ${section === 'all' ? '' : section + '-'}Einstellungen auf Standard zurücksetzen?`)) return;
  try {
    await apiResetSettings(section);
    await loadSettings();
    showSettingsToast();
  } catch (err) {
    console.error('Reset fehlgeschlagen:', err);
    apiLogError('error', `Settings reset: ${err.message}`, 'settings.js');
  }
}
