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
  CH: '🇨🇭', FR: '🇫🇷', DE: '🇩🇪', IT: '🇮🇹', AT: '🇦🇹',
  ES: '🇪🇸', NL: '🇳🇱', BE: '🇧🇪', PT: '🇵🇹', GB: '🇬🇧',
  XX: '🌍',
};

const S = {
  step: 1,
  adults: 2,
  children: [],
  travelStyles: [],
  mandatoryTags: [],
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

/** Build a 3-image gallery strip (overview + mood + customer). Returns '' if all null. */
function buildImageGallery(overview, mood, customer, altText) {
  if (!overview && !mood && !customer) return '';
  const alt = esc(altText || '');
  const img = (url, cls, caption) => url
    ? `<div class="${cls}"><img src="${esc(url)}" alt="${alt}" loading="lazy"
         data-lightbox-url="${esc(url)}" data-lightbox-caption="${esc(caption || altText || '')}"
         onerror="this.style.display='none'"></div>`
    : `<div class="${cls}"></div>`;
  return `<div class="img-gallery">
    ${img(overview, 'img-gallery-overview', altText + ' — Übersicht')}
    ${img(mood,     'img-gallery-mood',     altText + ' — Atmosphäre')}
    ${img(customer, 'img-gallery-customer', altText + ' — Besucher')}
  </div>`;
}

/** Open lightbox for a validated Unsplash URL. */
function openLightbox(url, caption) {
  const valid = url && (
    url.startsWith('https://images.unsplash.com/') ||
    url.startsWith('https://plus.unsplash.com/')
  );
  if (!valid) return;
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox-caption').textContent = caption || '';
  const overlay = document.getElementById('lightbox-overlay');
  overlay.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

/** Close the lightbox overlay. */
function closeLightbox() {
  const overlay = document.getElementById('lightbox-overlay');
  if (overlay) overlay.style.display = 'none';
  document.body.style.overflow = '';
}

// Event delegation for lightbox open/close
document.addEventListener('click', e => {
  const img = e.target.closest('[data-lightbox-url]');
  if (img) {
    openLightbox(img.dataset.lightboxUrl, img.dataset.lightboxCaption);
  } else if (e.target.id === 'lightbox-overlay') {
    closeLightbox();
  }
});
