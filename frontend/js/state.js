'use strict';

const TRAVEL_STYLES = [
  { id: 'adventure',    label: 'Abenteuer',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l4-8 4 4 4-6 4 10"/></svg>' },
  { id: 'relaxation',  label: 'Entspannung',    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2"/><path d="M12 6v6l4 2"/></svg>' },
  { id: 'culture',     label: 'Kultur',          icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M20 10v11M8 10v11M12 10v11M16 10v11"/></svg>' },
  { id: 'romantic',    label: 'Romantik',        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>' },
  { id: 'culinary',    label: 'Kulinarisch',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>' },
  { id: 'road_trip',   label: 'Road Trip',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>' },
  { id: 'nature',      label: 'Natur',           icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 8C8 10 5.9 16.17 3.82 21.34"/><path d="M21.54 11.37A11 11 0 0 0 10.27 8C8 8 5.94 9.13 4.37 11.37"/><path d="M3 21s2.18-4.15 9.59-5.36"/></svg>' },
  { id: 'city',        label: 'Städtereise',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>' },
  { id: 'wellness',    label: 'Wellness & Spa',  icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' },
  { id: 'sport',       label: 'Sport & Outdoor', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8l4 4-4 4-4-4 4-4z"/></svg>' },
  { id: 'group',       label: 'Gruppenreise',    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' },
  { id: 'kids',        label: 'Familienaktiv.',  icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="3"/><path d="M12 8v6M9 11h6M9 21l3-7 3 7"/></svg>' },
  { id: 'slow_travel', label: 'Slow Travel',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' },
  { id: 'party',       label: 'Nightlife',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>' },
];

const FLAGS = {
  CH: '<span class="flag-badge">CH</span>',
  FR: '<span class="flag-badge">FR</span>',
  DE: '<span class="flag-badge">DE</span>',
  IT: '<span class="flag-badge">IT</span>',
  AT: '<span class="flag-badge">AT</span>',
  ES: '<span class="flag-badge">ES</span>',
  NL: '<span class="flag-badge">NL</span>',
  BE: '<span class="flag-badge">BE</span>',
  PT: '<span class="flag-badge">PT</span>',
  GB: '<span class="flag-badge">GB</span>',
  XX: '<span class="flag-badge">??</span>',
};

const S = {
  step: 1,
  adults: 2,
  children: [],
  travelStyles: [],
  mandatoryTags: [],
  legs: [],
  jobId: null,
  sse: null,
  logs: [],
  apiCalls: 0,
  debugOpen: false,
  result: null,
  // Route Builder
  selectedStops: [],
  currentOptions: [],
  loadingOptions: false,
  confirmingRoute: false,
  // Accommodation Phase
  allStops: [],
  selectedAccommodations: {},
  prefetchedOptions: {},
  pendingSelections: {},
  allAccLoaded: false,
  accSelectionCount: 0,
};

// localStorage keys
const LS_FORM          = 'tp_v1_form';
const LS_ROUTE         = 'tp_v1_route';
const LS_ACCOMMODATIONS = 'tp_v1_accommodations';
const LS_RESULT        = 'tp_v1_result';

function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}

function lsGet(key) {
  try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; }
}

function lsClear(key) {
  try { localStorage.removeItem(key); } catch (e) {}
}

/**
 * Escape text and wrap any matched must-have terms in <strong>.
 * Safe to use with innerHTML.
 */
function highlightMustHaves(text, mustHaves) {
  let safe = esc(text);
  if (!mustHaves || mustHaves.length === 0) return safe;
  mustHaves.forEach(term => {
    if (!term) return;
    const escaped = esc(term);
    const re = new RegExp(escaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    safe = safe.replace(re, m => `<strong>${m}</strong>`);
  });
  return safe;
}

/** Escape user content for safe HTML insertion. */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Allow only http:// and https:// URLs.
 * Returns '' for javascript:, data:, or any other scheme.
 */
function safeUrl(url) {
  if (!url) return '';
  const s = String(url).trim();
  return (s.startsWith('https://') || s.startsWith('http://')) ? s : '';
}

/** Show a section, hide all others. */
function showSection(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
  if (typeof updateQuickSubmitBar === 'function') updateQuickSubmitBar();
}

/**
 * Build a hero photo component — one large image with click-to-open gallery.
 * @param {string[]} urls - Array of image URLs
 * @param {string} altText - Alt text for the image
 * @param {'lg'|'md'|'sm'} sizeClass - Size variant (lg=280px, md=200px, sm=140px)
 * @returns {string} HTML string
 */
function buildHeroPhoto(urls, altText, sizeClass = 'md') {
  if (!urls || !urls.length) return '';
  const alt = esc(altText || '');
  const urlsJson = JSON.stringify(urls.map(u => esc(u)));
  const countBadge = urls.length > 1
    ? `<span class="hero-photo-count">${urls.length} Fotos</span>`
    : '';
  return `
    <div class="hero-photo hero-photo--${sizeClass}" data-photo-urls='${urlsJson}'>
      <img src="${esc(urls[0])}" alt="${alt}" loading="lazy"
           data-lightbox-url="${esc(urls[0])}"
           data-lightbox-caption="${alt}"
           onerror="this.parentElement.classList.add('hero-photo-error')">
      ${countBadge}
    </div>`;
}

/**
 * Build a hero photo loading placeholder.
 * @param {'lg'|'md'|'sm'} sizeClass - Size variant
 * @returns {string} HTML string
 */
function buildHeroPhotoLoading(sizeClass = 'md') {
  return `<div class="hero-photo hero-photo--${sizeClass} hero-photo-loading"><div class="hero-photo-shimmer shimmer-elem"></div></div>`;
}

// Lightbox gallery state
let _lbUrls = [];
let _lbIndex = 0;

/** Open lightbox for any https:// or data: URL. */
function openLightbox(url, caption) {
  if (!url || (!url.startsWith('https://') && !url.startsWith('data:'))) return;
  const img = document.getElementById('lightbox-img');
  img.src = url;
  img.alt = caption || '';
  document.getElementById('lightbox-caption').textContent = caption || '';
  const counter = document.getElementById('lightbox-counter');
  if (counter) counter.textContent = _lbUrls.length > 1
    ? `${_lbIndex + 1} / ${_lbUrls.length}` : '';
  const overlay = document.getElementById('lightbox-overlay');
  overlay.dataset.single = _lbUrls.length === 1 ? 'true' : 'false';
  overlay.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

/** Navigate lightbox to prev (-1) or next (+1) image. */
function lightboxNav(dir) {
  if (_lbUrls.length < 2) return;
  _lbIndex = (_lbIndex + dir + _lbUrls.length) % _lbUrls.length;
  const url = _lbUrls[_lbIndex];
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox-caption').textContent =
    `${_lbIndex + 1}/${_lbUrls.length}`;
  const counter = document.getElementById('lightbox-counter');
  if (counter) counter.textContent = `${_lbIndex + 1} / ${_lbUrls.length}`;
  const overlay = document.getElementById('lightbox-overlay');
  overlay.dataset.single = _lbUrls.length === 1 ? 'true' : 'false';
}

/** Close the lightbox overlay. */
function closeLightbox() {
  const overlay = document.getElementById('lightbox-overlay');
  if (overlay) overlay.style.display = 'none';
  document.body.style.overflow = '';
}

// Event delegation for lightbox open/close
document.addEventListener('click', e => {
  // Hero-photo click → open lightbox with all photos from data-photo-urls
  const hero = e.target.closest('.hero-photo[data-photo-urls]');
  if (hero && !e.target.closest('button')) {
    e.stopPropagation();
    try {
      _lbUrls = JSON.parse(hero.dataset.photoUrls);
    } catch { _lbUrls = []; }
    if (_lbUrls.length === 0) return;
    _lbIndex = 0;
    openLightbox(_lbUrls[0], hero.querySelector('img')?.alt || '');
    return;
  }

  // Fallback: standalone lightbox-url elements
  const img = e.target.closest('[data-lightbox-url]');
  if (img) {
    e.stopPropagation();
    _lbUrls = [img.dataset.lightboxUrl];
    _lbIndex = 0;
    openLightbox(img.dataset.lightboxUrl, img.dataset.lightboxCaption);
  } else if (e.target.id === 'lightbox-overlay') {
    closeLightbox();
  }
});
