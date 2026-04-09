'use strict';

// Mode Picker — landing page overlay for choosing Rundreise / Erkunden / Ortsreise.
// Reads: S (state.js), t (i18n.js), showSection (state.js), lsSet (state.js).
// Provides: initModePicker, showModePicker.

// ---------------------------------------------------------------------------
// Icons (SVG strings, stroke-based, 32x32)
// ---------------------------------------------------------------------------

const ICONS = {
  rundreise: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M3 12h18M3 12l4-4m-4 4 4 4M21 12l-4-4m4 4-4 4"/>
  </svg>`,
  erkunden: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10"/>
    <polygon points="16.24,7.76 14.12,14.12 7.76,16.24 9.88,9.88"/>
  </svg>`,
  ortsreise: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/>
    <circle cx="12" cy="9" r="2.5"/>
  </svg>`,
};

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

/**
 * Render the mode picker cards into #mode-picker and attach click handlers.
 * Called once on app init. Safe to call multiple times (re-renders).
 */
function initModePicker() {
  const el = document.getElementById('mode-picker');
  if (!el) return;

  const modes = ['rundreise', 'erkunden', 'ortsreise'];
  const cardsHtml = modes.map((mode) => `
    <div class="mode-card" data-mode="${mode}" role="button" tabindex="0"
         aria-label="${t(`mode_picker.${mode}.name`)}">
      <div class="mode-card-icon">${ICONS[mode]}</div>
      <h3>${t(`mode_picker.${mode}.name`)}</h3>
      <p>${t(`mode_picker.${mode}.description`)}</p>
      <span class="mode-cta">${t('mode_picker.start_cta')}</span>
    </div>
  `).join('');

  el.innerHTML = `
    <p class="overline">REISE PLANEN</p>
    <h1>${t('mode_picker.title')}</h1>
    <p class="subtitle">${t('mode_picker.subtitle')}</p>
    <div class="mode-picker-cards">${cardsHtml}</div>
  `;

  el.querySelectorAll('.mode-card').forEach((card) => {
    card.addEventListener('click', () => _selectMode(card.dataset.mode));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') _selectMode(card.dataset.mode);
    });
  });
}

// ---------------------------------------------------------------------------
// Mode selection
// ---------------------------------------------------------------------------

/**
 * Set S.appMode and navigate to the correct section.
 * @param {string} mode - 'rundreise' | 'erkunden' | 'ortsreise'
 */
function _selectMode(mode) {
  S.appMode = mode;
  lsSet('app_mode', mode);
  if (mode === 'ortsreise') {
    showSection('form-section');
    if (typeof renderOrtsreiseForm === 'function') renderOrtsreiseForm();
  } else {
    showSection('form-section');
  }
}

/**
 * Show the mode picker overlay and clear the current appMode.
 */
function showModePicker() {
  S.appMode = null;
  lsSet('app_mode', null);
  showSection('mode-picker');
}
