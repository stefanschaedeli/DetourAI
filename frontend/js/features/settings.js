'use strict';

// Settings — settings page: per-agent model selection (9 AI agents), budget defaults, API keys.
// Reads: S (state.js), Router (router.js), t (i18n.js), apiOllamaHealth (api.js).
// Provides: openSettingsPage, closeSettingsPage, loadSettings.

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AGENT_META = {
  'route_architect':            { label: 'Route Architect',            get role() { return t('settings.route_architect_role'); } },
  'stop_options_finder':        { label: 'Stop Options Finder',        get role() { return t('settings.stop_options_role'); } },
  'region_planner':             { label: 'Region Planner',             get role() { return t('settings.region_planner_role'); } },
  'accommodation_researcher':   { label: 'Accommodation Researcher',   get role() { return t('settings.accommodation_role'); } },
  'activities':                 { label: 'Activities Agent',           get role() { return t('settings.activities_role'); } },
  'restaurants':                { label: 'Restaurants Agent',          get role() { return t('settings.restaurants_role'); } },
  'day_planner':                { label: 'Day Planner',                get role() { return t('settings.day_planner_role'); } },
  'travel_guide':               { label: 'Travel Guide',               get role() { return t('settings.travel_guide_role'); } },
  'trip_analysis':              { label: 'Trip Analysis',               get role() { return t('settings.trip_analysis_role'); } },
};

const MODEL_OPTIONS = [
  { value: 'claude-opus-4-5',   label: 'Claude Opus' },
  { value: 'claude-sonnet-4-5', label: 'Claude Sonnet' },
  { value: 'claude-haiku-4-5',  label: 'Claude Haiku' },
];

let _settingsData = null;
let _saveTimer = null;
let _previousSection = 'form-section';

// ---------------------------------------------------------------------------
// Page lifecycle
// ---------------------------------------------------------------------------

/** Shows the settings section and loads current settings from the backend. */
function openSettingsPage() {
  // Remember which section was active
  document.querySelectorAll('.section').forEach(s => {
    if (s.classList.contains('active') && s.id !== 'settings-section') {
      _previousSection = s.id;
    }
    s.classList.remove('active');
  });
  document.getElementById('settings-section').classList.add('active');
  if (location.pathname !== '/settings') {
    Router.navigate('/settings');
  }
  loadSettings();
}

/** Hides the settings section and restores the previously active section. */
function closeSettingsPage() {
  document.getElementById('settings-section').classList.remove('active');
  const prev = document.getElementById(_previousSection);
  if (prev) prev.classList.add('active');
  history.back();
}

/** Fetches settings from the backend and renders the full settings page. */
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
          ${t('settings.back_btn')}
        </button>
        <h2>${t('settings.page_title')}</h2>
      </div>

      ${_renderAccountSection()}
      ${_renderCategory(t('settings.ai_agents_section'), 'agent', _renderAgentCards(settings, defaults))}
      ${_renderCategory(t('form.budget_distribution_label'), 'budget', _renderBudgetSection(settings, defaults))}
      ${_renderCategory('API & Performance', 'api', _renderApiSection(settings, defaults))}
      ${_renderCategory('System', 'system', _renderSystemSection(settings, defaults, api_keys))}
    </div>
    <div class="settings-toast" id="settings-toast">Gespeichert</div>
  `;

  _bindAccountSection();
}

function _renderAccountSection() {
  return `
    <div class="settings-category" id="cat-account">
      <div class="settings-category-header" onclick="toggleSettingsCategory('account')">
        <h3>${t('settings.account_section')}</h3>
        <div class="settings-category-actions">
          <svg class="settings-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
            <path d="M6 9l6 6 6-6"/>
          </svg>
        </div>
      </div>
      <div class="settings-category-body open">
        <div class="settings-card">
          <h3>${t('settings.change_password_title')}</h3>
          <div class="settings-field">
            <label>${t('settings.current_password_label')}</label>
            <input type="password" id="current-password" placeholder="${t('settings.current_password_label')}" autocomplete="current-password">
          </div>
          <div class="settings-field">
            <input type="password" id="new-password" placeholder="${t('settings.new_password_placeholder')}" autocomplete="new-password">
          </div>
          <div class="settings-field">
            <input type="password" id="confirm-password" placeholder="${t('settings.confirm_password_placeholder')}" autocomplete="new-password">
          </div>
          <button id="change-password-btn" class="btn-primary">${t('settings.change_password_btn')}</button>
          <p id="password-change-msg" class="settings-msg" style="display:none"></p>
        </div>
      </div>
    </div>
  `;
}

function _bindAccountSection() {
  document.getElementById('change-password-btn')?.addEventListener('click', async () => {
    const current = document.getElementById('current-password').value;
    const newPw = document.getElementById('new-password').value;
    const confirm = document.getElementById('confirm-password').value;
    const msg = document.getElementById('password-change-msg');

    if (newPw !== confirm) {
      msg.textContent = t('settings.password_mismatch');
      msg.className = 'settings-msg error';
      msg.style.display = '';
      return;
    }

    const btn = document.getElementById('change-password-btn');
    btn.disabled = true;
    btn.textContent = 'Wird gespeichert…';

    try {
      await apiChangePassword(current, newPw);
      msg.textContent = t('settings.password_changed');
      msg.className = 'settings-msg success';
      ['current-password', 'new-password', 'confirm-password'].forEach(id => {
        document.getElementById(id).value = '';
      });
    } catch (err) {
      // Extract detail from HTTP error message (format: "HTTP 400: <detail>")
      const detail = err.message.replace(/^HTTP \d+:\s*/, '');
      msg.textContent = detail || t('settings.password_change_error');
      msg.className = 'settings-msg error';
    } finally {
      msg.style.display = '';
      btn.disabled = false;
      btn.textContent = t('settings.change_password_btn');
    }
  });
}

function _renderCategory(title, section, content) {
  return `
    <div class="settings-category" id="cat-${section}">
      <div class="settings-category-header" onclick="toggleSettingsCategory('${section}')">
        <h3>${esc(title)}</h3>
        <div class="settings-category-actions">
          <button class="settings-reset-btn" onclick="event.stopPropagation(); resetSettingsSection('${section}')" title="${t('settings.reset_to_defaults_title')}">
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
  const useLocalLlm = settings['system.use_local_llm'];
  const localModel = settings['system.ollama_model'] || '';

  return Object.entries(AGENT_META).map(([key, meta]) => {
    const modelKey = `agent.${key}.model`;
    const tokensKey = `agent.${key}.max_tokens`;
    const currentModel = settings[modelKey] || defaults[modelKey];
    const currentTokens = settings[tokensKey] || defaults[tokensKey];
    const isDefault = currentModel === defaults[modelKey] && currentTokens === defaults[tokensKey];

    const localBadge = useLocalLlm
      ? `<span class="settings-badge badge-ok">${esc(t('settings.local_llm_agents_note').replace('{model}', localModel || 'Ollama'))}</span>`
      : '';

    return `
      <div class="settings-agent-card">
        <div class="settings-agent-header" onclick="toggleAgentCard(this)">
          <div class="settings-agent-info">
            <span class="settings-agent-name">${esc(meta.label)}</span>
            <span class="settings-badge">${esc(meta.role)}</span>
            ${localBadge}
          </div>
          <div class="settings-agent-model-badge ${_modelClass(currentModel)}">
            ${esc(_modelLabel(currentModel))}
          </div>
        </div>
        <div class="settings-agent-body">
          <div class="settings-row">
            <label>${t('settings.model_label')}</label>
            <select onchange="saveSetting('${modelKey}', this.value)" ${useLocalLlm ? 'disabled' : ''}>
              ${MODEL_OPTIONS.map(m => `<option value="${m.value}" ${m.value === currentModel ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}
            </select>
          </div>
          <div class="settings-row">
            <label>${t('settings.max_tokens_label')}</label>
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
    ${_row(t('settings.accommodation_pct_label'), _slider('budget.accommodation_pct', settings, 5, 80, 1, '%'))}
    ${_row(t('settings.fallback_accommodation_label'), _numberInput('budget.fallback_accommodation_chf', settings, 10, 500, 'CHF/Nacht'))}
    ${_row(t('settings.fallback_activities_label'), _numberInput('budget.fallback_activities_chf', settings, 10, 300, 'CHF/Stop'))}
    ${_row(t('settings.fallback_food_label'), _numberInput('budget.fallback_food_chf', settings, 10, 200, 'CHF/Nacht'))}
    ${_row(t('settings.fuel_label'), _numberInput('budget.fuel_chf_per_hour', settings, 5, 50, 'CHF/Stunde'))}
    ${_row(t('settings.accommodation_mult_min_label'), _numberInput('budget.acc_multiplier_min', settings, 0.5, 2.0, '', 0.05))}
    ${_row(t('settings.accommodation_mult_max_label'), _numberInput('budget.acc_multiplier_max', settings, 0.5, 2.0, '', 0.05))}
  `;
}

function _renderApiSection(settings, defaults) {
  return `
    ${_row(t('settings.nominatim_delay_label'), _numberInput('api.nominatim_delay_ms', settings, 100, 2000, 'ms'))}
    ${_row(t('settings.nominatim_timeout_label'), _numberInput('api.nominatim_timeout_s', settings, 1, 30, 's'))}
    ${_row(t('settings.osrm_timeout_label'), _numberInput('api.osrm_timeout_s', settings, 1, 30, 's'))}
    ${_row(t('settings.wikipedia_timeout_label'), _numberInput('api.wikipedia_timeout_s', settings, 1, 30, 's'))}
    ${_warningRow('Max Wiederholungen', _numberInput('api.retry_max_attempts', settings, 1, 10, ''))}
    ${_row('Parallele Unterkunftssuche', _numberInput('api.accommodation_parallelism', settings, 1, 5, ''))}
  `;
}

function _renderSystemSection(settings, defaults, apiKeys) {
  const testMode = settings['system.test_mode'];
  const useLocalLlm = settings['system.use_local_llm'];
  const ollamaEndpoint = settings['system.ollama_endpoint'] || '';
  const ollamaModel = settings['system.ollama_model'] || '';
  return `
    <div class="settings-row">
      <label>${t('settings.use_local_llm_label')}</label>
      <div class="settings-toggle-wrapper">
        <label class="settings-toggle">
          <input type="checkbox" id="local-llm-toggle" ${useLocalLlm ? 'checked' : ''}
            onchange="saveSetting('system.use_local_llm', this.checked); _toggleLocalLlmDetails(this.checked)">
          <span class="settings-toggle-slider"></span>
        </label>
        <span class="settings-toggle-label">${useLocalLlm ? 'An' : 'Aus'}</span>
      </div>
    </div>
    <div id="local-llm-details" style="display:${useLocalLlm ? '' : 'none'}">
      <div class="settings-row">
        <label>${t('settings.ollama_endpoint_label')}</label>
        <div class="settings-input-group">
          <input type="text" value="${esc(ollamaEndpoint)}"
            placeholder="${t('settings.ollama_endpoint_placeholder')}"
            onchange="debounceSave('system.ollama_endpoint', this.value)">
        </div>
      </div>
      <div class="settings-row">
        <label>${t('settings.ollama_model_label')}</label>
        <div class="settings-input-group">
          <input type="text" value="${esc(ollamaModel)}"
            placeholder="${t('settings.ollama_model_placeholder')}"
            onchange="debounceSave('system.ollama_model', this.value)">
        </div>
      </div>
      <div class="settings-row">
        <label>${t('settings.ollama_test_btn')}</label>
        <button class="btn-primary" onclick="_testOllamaConnection()">${t('settings.ollama_test_btn')}</button>
      </div>
      <div id="ollama-status" style="display:none" class="settings-row">
        <label></label>
        <div id="ollama-status-content"></div>
      </div>
    </div>
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

/* ── Local LLM helpers ── */

function _toggleLocalLlmDetails(enabled) {
  const details = document.getElementById('local-llm-details');
  if (details) details.style.display = enabled ? '' : 'none';
  // Update toggle label to match new state
  const toggleLabel = document.querySelector('#local-llm-toggle')
    ?.closest('.settings-toggle-wrapper')
    ?.querySelector('.settings-toggle-label');
  if (toggleLabel) toggleLabel.textContent = enabled ? 'An' : 'Aus';
}

async function _testOllamaConnection() {
  const statusEl = document.getElementById('ollama-status');
  const contentEl = document.getElementById('ollama-status-content');
  if (!statusEl || !contentEl) return;
  statusEl.style.display = '';
  contentEl.textContent = '…';
  try {
    const result = await apiOllamaHealth();
    const models = Array.isArray(result.models) ? result.models : [];
    contentEl.textContent = '';
    const badge = document.createElement('span');
    badge.className = 'settings-badge badge-ok';
    badge.textContent = t('settings.ollama_status_ok');
    contentEl.appendChild(badge);
    if (models.length) {
      const modelNote = document.createElement('div');
      modelNote.className = 'settings-toggle-label';
      modelNote.textContent = t('settings.ollama_available_models') + ': ' + models.join(', ');
      contentEl.appendChild(modelNote);
    }
  } catch (err) {
    contentEl.textContent = '';
    const badge = document.createElement('span');
    badge.className = 'settings-badge badge-err';
    badge.textContent = t('settings.ollama_status_error');
    contentEl.appendChild(badge);
  }
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
  if (!await showConfirm(`Alle ${section === 'all' ? '' : section + '-'}Einstellungen auf Standard zur\u00fccksetzen?`)) return;
  try {
    await apiResetSettings(section);
    await loadSettings();
    showSettingsToast();
  } catch (err) {
    console.error('Reset fehlgeschlagen:', err);
    apiLogError('error', `Settings reset: ${err.message}`, 'settings.js');
  }
}
