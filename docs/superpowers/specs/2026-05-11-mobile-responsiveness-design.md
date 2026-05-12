# Mobile Responsiveness Pass — Design Spec

**Date:** 2026-05-11
**Status:** Draft for review
**Scope:** Frontend only (HTML/CSS/JS). No backend or business-logic changes.

---

## Context

DetourAI's frontend has a working desktop UI and partial mobile support: a viewport meta tag, an off-canvas sidebar with hamburger toggle, mode-picker / login / settings that collapse at narrow widths, guide tabs that horizontally scroll, and a full-screen lightbox. However a read-only audit (three parallel explorer agents) surfaced **seven systemic problem areas** that prevent the app from being genuinely usable on a phone or comfortably usable on a tablet:

1. The 5-step trip form keeps 2-column input rows on phones (legs, dates, summary, budget) → cramped controls and horizontal-scroll risk at 360 px.
2. The header packs 8–9 items into a single non-wrapping row.
3. Drag-to-reorder for stops and days uses HTML5 drag events that **never fire on touch** — phone users cannot reorder anything.
4. Touch targets are below the 44 × 44 px guideline in many places (step circles 28 px, `.btn-sm` ~30 px, `.mode-btn` ~24 px, leg-delete ~24 px, header buttons 32 px, map pins 28 px, tag remove ×, nights input 50 px).
5. iOS Safari auto-zooms when any `<input>` font-size is < 16 px (login inputs at 15 px, nights input at browser default).
6. Body scroll lock is missing for the unified SSE overlay, the feedback modal, `showConfirm`, and the replace-stop modal — background page scrolls behind the dialog.
7. Breakpoint values are scattered (479, 480, 500, 600, 640, 767, 768, 769, 1023, 1100) with a JS-vs-CSS mismatch at 768 px; no `env(safe-area-inset-*)` so iPhone notch/home-indicator cuts into fixed bars; missing `theme-color`, `apple-touch-icon`, `viewport-fit=cover`.

Intended outcome: every existing flow (mode-picker → 5-step form → SSE progress → guide viewer with overview/days/map/share/budget tabs, edit mode, settings, auth, travels drawer, feedback) works comfortably on phone (≈ 360–430 px), small tablet (≈ 600–820 px), and large tablet (≈ 820–1024 px) in both orientations — without regressing the desktop experience.

---

## Decisions (locked with user)

| # | Decision | Choice |
|---|---|---|
| 1 | Scope | Phone + tablet, **all flows** |
| 2 | Touch-target strictness | **Strict 44 × 44 on ≤ 768 px** |
| 3 | iOS zoom fix | **Bump inputs to 16 px on mobile only** |
| 4 | Reorder UX on touch | **Explicit "Reihenfolge ändern" mode with ▲/▼ buttons** |
| 5 | Header on narrow screens | **Collapse non-essential items into settings menu** |
| 6 | Mobile meta | **Minimal mobile meta** (theme-color, apple-touch-icon, viewport-fit, safe-area-inset). **No** PWA manifest. |
| 7 | Breakpoints | **3 canonical tokens**: `--bp-mobile: 600px`, `--bp-tablet: 900px`. Standardize sidebar JS to 600 px. Don't retroactively rewrite untouched media queries. |
| 8 | Step 1 layout on mobile | **Stack all to single column on ≤ 600 px** (Von, Nach, Start, Ende) |
| 9 | Scroll lock | **Shared `.scroll-lock` body class**, wired from every modal/overlay opener |
| 10 | Verification | **Manual checklist on real devices/emulators** |
| 11 | Commit bundling | **One commit per logical area**, each its own patch tag (~6 total) |
| 12 | Guide sticky map | **Drop sticky on mobile** (becomes normal block; auto-collapse already exists) |

---

## Architecture

The work splits into **six logical areas (A–F)**, each shippable independently with its own commit and tag. Area A (foundations) must land first because B–F depend on the breakpoint tokens, scroll-lock class, and safe-area variables it introduces.

```
A. Foundations
   ├── A1 — Mobile meta in <head>
   ├── A2 — Canonical breakpoint tokens + sidebar JS alignment
   ├── A3 — .scroll-lock body class + rewire existing locks
   └── A4 — iOS auto-zoom fix (inputs ≥ 16 px on mobile)
B. Header restructure
C. 5-step form
D. Route-builder + guide viewer + maps + reorder mode
E. Overlays + dialogs + standalone pages
F. Touch-target sweep
```

Areas B–F can ship in any order after A. None of them depends on another.

---

## Area-by-area design

### A. Foundations

#### A1. Mobile meta (`frontend/index.html`)

In `<head>` add:

```html
<meta name="theme-color" content="#1a73e8">  <!-- or current brand colour, TBD from CSS vars -->
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/icon-180.png">  <!-- reuse / create from existing logo -->
```

In `styles.css` `:root` define `--safe-top`, `--safe-bottom`, `--safe-left`, `--safe-right` mapped to `env(safe-area-inset-*)` with `0px` fallback. Apply to:
- `.app-header` → `padding-top: max(var(--safe-top), 0px)`
- `.feedback-fab` → `bottom: calc(16px + var(--safe-bottom))`
- `.app-toast`, `.settings-toast` → `bottom: calc(24px + var(--safe-bottom))`
- `.quick-submit-bar` → `padding-bottom: calc(8px + var(--safe-bottom))`

#### A2. Canonical breakpoints

In `styles.css` `:root`:

```css
--bp-mobile: 600px;
--bp-tablet: 900px;
```

CSS custom properties can't be used inside `@media` query conditions directly — they're documentation tokens. New media queries written during this pass use the literal `(max-width: 600px)` and `(max-width: 900px)` and reference the token in a comment.

Update `frontend/js/features/sidebar.js:336` to check `window.innerWidth > 600` instead of `> 768`. The drawer / overlay logic stays; only the boundary moves.

#### A3. `.scroll-lock` class

```css
body.scroll-lock { overflow: hidden; touch-action: none; }
```

Wire from:
- `frontend/js/communication/unified-overlay.js` — show/hide
- `frontend/js/features/feedback.js` — modal open/close
- `frontend/js/core/api.js` — `showConfirm()` open/close
- `frontend/js/guide/guide-edit.js` — replace-stop modal open/close
- `frontend/js/core/state.js` (lightbox) — replace inline `document.body.style.overflow` calls with class toggle
- `frontend/js/features/travels.js` — replace inline `document.body.style.overflow` calls with class toggle

#### A4. iOS auto-zoom fix

```css
@media (max-width: 600px) {
  input, select, textarea { font-size: 16px; }
}
```

Affects `.nights-input` and login inputs (currently 15 px). Desktop unchanged.

---

### B. Header restructure

**Markup** (`frontend/index.html:19–66`): no structural change, just toggle visibility via CSS classes.

**CSS** (new rules at end of `styles.css`):

```css
@media (max-width: 600px) {
  .app-subtitle,
  .app-version,
  .btn-my-travels,
  .header-username,
  .btn-admin,
  .btn-logout { display: none; }
}
@media (max-width: 900px) and (min-width: 601px) {
  .app-subtitle,
  .app-version { display: none; }
}
```

**Settings dropdown** (`frontend/js/features/settings.js` — extend the dropdown DOM):

On mobile only, prepend a "Konto" section to `.settings-menu` containing:
- Username text (read-only)
- Version text
- "Meine Reisen" link (calls existing `openTravelsDrawer`)
- "Admin" link (only if `S.isAdmin`)
- "Abmelden" link (calls existing logout)

Use a `window.matchMedia('(max-width: 600px)')` check at dropdown-open time to conditionally inject these rows. Desktop dropdown stays exactly as today.

---

### C. 5-step form

**Step indicator** (`styles.css:614–635`): on ≤ 600 px, switch container to `overflow-x: auto; scroll-snap-type: x mandatory;`. Each `.step` becomes `scroll-snap-align: center`. Show label only for active step (`.step.active .step-label { display: block; }`, others `display: none`). On scroll, JS scrolls the active step into view via `scrollIntoView({inline:'center'})` whenever step changes — add to existing step-change handler in `form.js`.

**Step 1 — Route legs** (`styles.css:3431–3460`):
```css
@media (max-width: 600px) {
  .leg-location-row,
  .leg-date-row { grid-template-columns: 1fr; }
  .input-sm { width: 100%; }
  .leg-header { flex-wrap: wrap; }
  .leg-delete-btn { min-width: 44px; min-height: 44px; }
}
```

**Step 2 — Travellers**: verify `.adults-counter button` (already 44 × 44) and `.child-row .btn-icon` (uses `.btn-icon` class, already 44 × 44). No layout change; A4 covers the number-input zoom.

**Step 3 — Activities**:
```css
@media (max-width: 600px) {
  .tag-input-field { min-width: 0; flex: 1; }
  .tag button { min-width: 32px; min-height: 32px; padding: 8px; }
}
```

**Step 4 — Accommodation**: already collapses via existing `.form-row` rule. F (touch sweep) handles `.acc-style` / `.must-have` chip sizes.

**Step 5 — Budget**:
```css
@media (max-width: 600px) {
  .budget-slider-row { flex-direction: column; align-items: stretch; gap: 4px; }
  .budget-slider-label { width: 100%; }
  .budget-preview { flex-wrap: wrap; }
}
```

**Step 6 — Summary**:
```css
@media (max-width: 600px) {
  .summary-row { flex-direction: column; gap: 4px; }
  .summary-label { min-width: 0; }
}
```

---

### D. Route-builder + guide viewer + maps + reorder mode

**Guide tabs fade hint** — add `::after` gradient mask on `.guide-tabs` (`styles.css:1494`) on mobile to indicate horizontal scroll.

**Sticky map → normal block on mobile**:
```css
@media (max-width: 600px) {
  .guide-map-section { position: static; }
  .stop-toggle { position: static; }
}
```

Keep `_initMapCollapse` (`guide-map.js:143–152`) — auto-collapse on first load remains.

**Map pin sizes** (`styles.css:5597–5612`): grow `.guide-marker-num` to 36 × 36 default, 44 × 44 when `.selected`. (Marker hit area in Google Maps extends beyond the visible badge, so 36 is acceptable for passive markers.)

**Click-to-add popup** (`styles.css:1770–1801`):
```css
.click-to-add-popup { max-width: calc(100vw - 32px); }
.popup-add-btn { min-height: 44px; padding: 10px 16px; }
```

**Stop card layout on phone** — keep horizontal but compact:
```css
@media (max-width: 600px) {
  .stop-card-row .stop-card-photo { width: 72px; aspect-ratio: 1; }
  .stop-card-meta { flex-direction: column; }
}
```

**Share row** on very narrow screens (`styles.css:5673–5679`):
```css
@media (max-width: 480px) {
  .share-toggle-container { flex-direction: column; align-items: stretch; }
  .share-url-input { max-width: none; }
}
```

**Reorder mode** (new feature):

UI: a new button "Reihenfolge ändern" in the days-tab and stops-tab edit toolbars (visible only when edit-mode is active). Tapping it sets `body.dataset.reorderMode = 'on'` and:
- HTML5 drag handles hide (`[data-reorder-mode="on"] .stop-edit-drag, [data-reorder-mode="on"] .day-edit-drag { display: none; }`)
- Each stop/day card receives two injected buttons `<button class="reorder-up">▲</button> <button class="reorder-down">▼</button>` (44 × 44, full-opacity background, sit at the right edge of the card)
- Click handlers call the **existing reorder JS** (`guide-edit.js` already has functions for `moveStopUp/Down` and `moveDayUp/Down` invoked by drag drop — extract or expose them)
- The toolbar label changes to "Fertig" which removes `data-reorder-mode` and removes the injected buttons

Files: `guide-edit.js` (mode toggle + button injection), `guide-stops.js` and `guide-days.js` (extract reorder functions if not already callable from outside), `styles.css` (reorder-mode rules). Drag-to-reorder on desktop stays intact and remains the default — reorder mode is the **fallback path** for touch users, but it works on desktop too (clickable arrows).

---

### E. Overlays + dialogs + standalone pages

**Unified overlay** (`styles.css:6347–6358`):
```css
@media (max-width: 600px) {
  .uo-card { max-width: 92vw; max-height: calc(100dvh - 32px); margin: 16px; }
  .uo-debug-log { max-height: 140px; }
}
```

**Toasts** (`styles.css:5841–5906`):
```css
@media (max-width: 480px) {
  .app-toast { left: 16px; right: 16px; max-width: none; }
}
```
Also recompute `bottom` stacking math in `api.js:494–496` to include safe-area.

**Travels drawer cards** (`styles.css:2643–2663`):
```css
@media (max-width: 600px) {
  .travel-card { flex-wrap: wrap; }
  .travel-card-actions { width: 100%; justify-content: flex-end; }
}
```

**Settings page**: already collapses at 600 px. Just verify after the column switch:
- `.settings-row select { min-height: 44px; }`
- Settings dropdown's right-anchor doesn't clip when invoked from a narrow viewport — add `max-width: calc(100vw - 16px); right: 8px;` on ≤ 600 px.

**Auth**: A4 covers login input font-size. Nothing else needed.

---

### F. Touch-target sweep (≤ 768 px)

Single block of overrides at the end of `styles.css`:

```css
@media (max-width: 768px) {
  .btn-sm { min-height: 44px; padding: 10px 18px; }
  .btn-my-travels,
  .app-header .btn-secondary { min-height: 44px; height: auto; }
  .settings-btn { min-width: 44px; min-height: 44px; }
  .mode-btn { padding: 10px 14px; min-height: 44px; }
  .tag button { min-width: 32px; min-height: 32px; padding: 8px; }
  .step-indicator .step::before {
    content: ''; position: absolute; inset: -8px; /* invisible 44px hit area */
  }
  .lightbox-prev, .lightbox-next { min-width: 44px; min-height: 44px; }
}
```

---

## Critical files

- `frontend/index.html` — `<head>` meta (A1), header markup (B optional)
- `frontend/styles.css` — all areas; ≈ 80–120 new lines, no rewrites of existing rules
- `frontend/js/features/sidebar.js` — JS boundary 768 → 600 (A2)
- `frontend/js/features/settings.js` — mobile "Konto" section in dropdown (B)
- `frontend/js/features/form.js` — step-indicator scroll-into-view (C)
- `frontend/js/communication/unified-overlay.js` — scroll-lock (A3)
- `frontend/js/features/feedback.js` — scroll-lock (A3)
- `frontend/js/core/api.js` — scroll-lock in showConfirm; toast safe-area math (A3, E)
- `frontend/js/core/state.js` — lightbox scroll-lock class (A3)
- `frontend/js/features/travels.js` — drawer scroll-lock class (A3)
- `frontend/js/guide/guide-edit.js` — reorder mode + replace-modal scroll-lock (A3, D)
- `frontend/js/guide/guide-stops.js`, `guide-days.js` — expose reorder functions (D)
- `frontend/js/guide/guide-map.js` — no change (existing collapse stays)

Reuses existing functions:
- `openTravelsDrawer()` in `travels.js:84–92` (for header collapse → settings menu)
- `_initMapCollapse()` in `guide-map.js:143–152` (kept as-is, sticky just stops conflicting)
- Existing reorder logic in `guide-edit.js` (extracted/exposed, not rewritten)

---

## Verification checklist

Run through this matrix in Chrome DevTools device mode + at least one real iOS Safari and one real Android Chrome before declaring done.

**Viewports**: iPhone SE (375 × 667), iPhone 14 Pro (393 × 852), Pixel 7 (412 × 915), iPad mini (768 × 1024), iPad Pro 11" (834 × 1194) — portrait and landscape for each.

**Per viewport, walk through:**

1. **Mode-picker**: cards fit; tap Roadtrip / Ortsreise.
2. **5-step form**:
   - Step 1 — add 2 legs, set 4 locations + 4 dates, verify no horizontal scroll, leg-delete tappable.
   - Step 2 — adults +/-, add 2 children, change ages, remove one.
   - Step 3 — add 3 tags, remove the middle one.
   - Step 4 — adjust accommodation chips, hotel-radius slider.
   - Step 5 — drag all 3 budget sliders.
   - Step 6 — verify summary key/value readable.
   - Step nav — Back/Next buttons reachable, step indicator scrolls.
3. **SSE generation overlay**: starts, progress bar updates, tasks list scrolls inside card, debug-log expands without breaking layout, background does not scroll.
4. **Guide overview tab**: stats grid, hero photos, day summaries readable.
5. **Guide days tab**: scroll through days, stop cards readable, photos fit, tap into a stop.
6. **Guide map tab**: map fills width, pins tappable, infowindow fits.
7. **Edit mode (days)**: enter edit, tap "Reihenfolge ändern", use ▲▼ to move a day, exit reorder mode, replace a stop via modal — modal scrolls internally, background does not.
8. **Share tab**: copy link works, link input readable.
9. **Settings**: open dropdown, tap into settings page, expand categories, change a setting, verify toast appears within viewport.
10. **Travels drawer**: open, see card list, tap a card's actions (load, delete, rename) — actions reachable, no overflow.
11. **Feedback FAB**: tap, write feedback, submit, toast appears.
12. **Auth**: log out, log in, verify keyboard doesn't push form off-screen.
13. **iOS notch**: header doesn't sit under status bar; FAB / toasts don't sit under home indicator.
14. **No auto-zoom** on any input focus on iOS Safari.

**Pass criteria**: every viewport completes the full walk-through without horizontal scroll, with all tap targets reachable, and without any text or control clipped.

---

## Commit plan

Each area = one commit + one patch tag. Six tags total. After each commit:
1. Update `<span class="app-version">` in `frontend/index.html`.
2. `git add` touched files, `git commit -m "type: beschreibung"` (German body, English type prefix).
3. `git tag vX.X.Y` (next patch from `git tag --sort=-v:refname | head -1`).
4. `git push && git push --tags`.

Order:
1. **A** — foundations (meta, breakpoints, scroll-lock, iOS zoom)
2. **B** — header restructure
3. **C** — 5-step form
4. **D** — guide viewer + maps + reorder mode
5. **E** — overlays + dialogs + standalone pages
6. **F** — touch-target sweep

If a single area produces a regression on desktop, that commit can be reverted in isolation without unwinding the rest.
