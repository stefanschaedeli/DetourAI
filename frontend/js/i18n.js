'use strict';

/**
 * Lightweight i18n module for DetourAI.
 * Provides t(key, params) for translations, setLocale()/getLocale() for language switching.
 * Loaded before all other app modules so t() is available globally.
 */

(function () {
  const SUPPORTED_LANGS = ['de', 'en', 'hi'];
  const DEFAULT_LANG = 'de';
  const STORAGE_KEY = 'tp_v1_lang';

  let _locale = DEFAULT_LANG;
  let _translations = {};
  let _loaded = false;

  /** Read saved locale or fall back to default. */
  function getLocale() {
    return _locale;
  }

  /** Load a locale JSON file synchronously (small files, ~5-10 KB). */
  function _loadTranslations(lang) {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', `/i18n/${lang}.json`, false); // synchronous
      xhr.send();
      if (xhr.status === 200) {
        _translations = JSON.parse(xhr.responseText);
        return true;
      }
    } catch (e) {
      console.error(`[i18n] Failed to load ${lang}.json:`, e);
    }
    return false;
  }

  /**
   * Translate a key with optional parameter interpolation.
   * t('loading.requests_running', {count: 3}) → "3 Anfragen laufen…"
   * Falls back to key itself if translation missing.
   */
  function t(key, params) {
    let val = _translations[key];
    if (val === undefined) return key;
    if (params) {
      Object.keys(params).forEach(function (k) {
        val = val.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
      });
    }
    return val;
  }

  /** Update all elements with data-i18n attribute. */
  function applyStaticTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      const key = el.getAttribute('data-i18n');
      const attr = el.getAttribute('data-i18n-attr');
      const translated = t(key);
      if (translated === key && !_translations[key]) return; // no translation found
      if (attr) {
        el.setAttribute(attr, translated);
      } else {
        el.textContent = translated;
      }
    });
  }

  /**
   * Switch locale: load translations, update DOM, persist preference.
   * Returns true on success.
   */
  function setLocale(lang) {
    if (!SUPPORTED_LANGS.includes(lang)) lang = DEFAULT_LANG;
    if (!_loadTranslations(lang)) {
      console.error(`[i18n] Could not load locale ${lang}, falling back to ${DEFAULT_LANG}`);
      if (lang !== DEFAULT_LANG) {
        _loadTranslations(DEFAULT_LANG);
        lang = DEFAULT_LANG;
      }
    }
    _locale = lang;
    _loaded = true;
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;

    // Update page title
    const titleKey = _translations['app.title'];
    if (titleKey) document.title = titleKey;

    applyStaticTranslations();
    return true;
  }

  /** Initialize i18n on page load. */
  function initI18n() {
    const saved = localStorage.getItem(STORAGE_KEY);
    const lang = (saved && SUPPORTED_LANGS.includes(saved)) ? saved : DEFAULT_LANG;
    setLocale(lang);
  }

  /**
   * Map the current i18n locale to a BCP 47 locale tag suitable for
   * Intl / toLocaleString() / toLocaleDateString() calls.
   */
  function getFormattingLocale() {
    const map = { de: 'de-CH', en: 'en-GB', hi: 'hi-IN' };
    return map[_locale] || 'de-CH';
  }

  // Expose globally
  window.t = t;
  window.getLocale = getLocale;
  window.setLocale = setLocale;
  window.getFormattingLocale = getFormattingLocale;
  window.applyStaticTranslations = applyStaticTranslations;
  window.initI18n = initI18n;
  window.SUPPORTED_LANGS = SUPPORTED_LANGS;
})();
