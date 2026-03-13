# Unified Photo Component & Route-Builder UI Redesign

**Date:** 2026-03-13
**Status:** Draft

---

## Summary

Three interconnected changes to unify the visual experience:

1. **Unified Hero-Photo Component** — Replace all `photo-strip` galleries with a single hero image + lightbox pattern
2. **Region-Plan UI Enhancement** — Add teaser, highlights, and images to region cards (backend + frontend)
3. **Route-Builder Unified UI** — Redesign the route-builder page to match the accommodation/guide page patterns

---

## 1. Unified Hero-Photo Component

### Problem
The current `buildPhotoGallery()` in `state.js` renders a horizontal strip of small images. This looks cluttered and inconsistent. Different sections use slightly different photo layouts.

### Solution
Replace `buildPhotoGallery()` with `buildHeroPhoto()` — a single function that renders one large hero image with a click-to-open gallery.

### Specification

**Function:** `buildHeroPhoto(urls, altText, sizeClass = 'md')`

**Returns HTML:**
```html
<div class="hero-photo hero-photo--{sizeClass}" data-photo-urls='{json}'>
  <img src="{urls[0]}" alt="{altText}" loading="lazy">
  <span class="hero-photo-count">1/{urls.length}</span>  <!-- only if urls.length > 1 -->
</div>
```

**CSS sizing classes:**
- `.hero-photo--lg` → height: 280px (Guide stop headers)
- `.hero-photo--md` → height: 200px (Option cards, region cards, accommodation cards)
- `.hero-photo--sm` → height: 140px (Activities, restaurants, compact views)

**CSS styling:**
- `width: 100%`, `object-fit: cover`, `border-radius` inherited from parent card
- `.hero-photo-count` badge: bottom-right, semi-transparent dark background, white text, small font
- `cursor: pointer` on the entire component
- Shimmer placeholder while loading (reuse existing `.shimmer-elem` pattern)

**Behavior:**
- Click anywhere on the hero photo → opens existing lightbox with all images
- Existing lightbox (arrow keys, prev/next, close) remains unchanged
- If no images available → show gradient placeholder (reuse existing SVG gradient fallback from `maps.js`)

**Loading placeholder:**
```html
<div class="hero-photo hero-photo--{sizeClass} hero-photo-loading">
  <div class="hero-photo-shimmer shimmer-elem"></div>
</div>
```

### Migration: Where to replace

| Location | File | Current | New | Size |
|----------|------|---------|-----|------|
| Stop option cards | route-builder.js | `photo-strip` | `hero-photo` | `md` |
| Region plan cards | route-builder.js | (none) | `hero-photo` | `md` |
| Accommodation cards | accommodation.js | `photo-strip` (vertical left panel) | `hero-photo` (top) | `md` |
| Guide stop header | guide.js | `photo-strip` | `hero-photo` | `lg` |
| Guide accommodation | guide.js | `photo-strip` | `hero-photo` | `sm` |
| Guide activities | guide.js | `photo-strip` | `hero-photo` | `sm` |
| Guide restaurants | guide.js | `photo-strip` | `hero-photo` | `sm` |

**Breaking change for accommodation cards:** Currently horizontal layout (photo left, content right). Changes to vertical layout (photo top, content below) — consistent with option cards. The `acc-option-card` CSS changes from `flex-direction: row` to `flex-direction: column`.

### Backward compatibility
- `buildPhotoGallery()` remains as deprecated wrapper calling `buildHeroPhoto()` during migration
- Remove after all call sites are migrated

---

## 2. Region-Plan UI Enhancement

### Problem
Region cards only show name + reason. Users can't visualize why a region fits — no images, no detailed description, no highlights.

### Backend Changes

**Model update** (`backend/models/trip_leg.py`):
```python
class RegionPlanItem(BaseModel):
    name: str = Field(max_length=200)
    lat: float
    lon: float
    reason: str = Field(max_length=500)
    teaser: str = Field(default="", max_length=300)       # NEW
    highlights: list[str] = Field(default_factory=list)    # NEW (3-5 items)
```

**Agent update** (`backend/agents/region_planner.py`):
- Update `REGION_SCHEMA` to include `teaser` and `highlights` in the JSON example
- Update system prompt to request these fields with guidance:
  - `teaser`: One-sentence summary of the region's appeal (German)
  - `highlights`: 3-5 key attractions or reasons to visit
- Token limit stays at 4096 (sufficient for the additional fields)

**No endpoint changes needed** — `model_dump()` automatically includes new fields.

### Frontend Changes

**Region cards** become structured cards similar to option cards:
```html
<div class="region-card" draggable="true" data-index="{i}">
  <div class="hero-photo hero-photo--md hero-photo-loading">
    <div class="hero-photo-shimmer shimmer-elem"></div>
  </div>
  <div class="region-card-body">
    <div class="region-card-header">
      <span class="region-card-number">{i+1}</span>
      <h3>{name}</h3>
      <button class="btn btn-sm btn-outline">Ersetzen</button>
    </div>
    <p class="region-teaser">{teaser}</p>
    <ul class="region-highlights">
      <li>{highlight}</li>
      ...
    </ul>
    <p class="region-reason">{reason}</p>
  </div>
  <div class="region-drag-handle">⠿</div>
</div>
```

**Image loading:** Use `_lazyLoadEntityImages(card, region.name, region.lat, region.lon, 'city')` — same pattern as option cards.

---

## 3. Route-Builder Unified UI

### Problem
The route-builder page uses a flat, minimal layout that doesn't match the structured panel pattern used in accommodation and guide sections.

### Changes

#### 3a. Page Header
**Current:** Simple flex row with h2 + back button.
**New:** Same pattern as accommodation-header:
```html
<div class="route-builder-header">
  <div>
    <h2>Route aufbauen</h2>
    <p class="route-builder-subtitle">{segment info, days remaining}</p>
  </div>
  <button class="btn btn-secondary">Zurück zum Formular</button>
</div>
```

#### 3b. Route Status → Integrated into header subtitle
Remove separate `.route-status` div. Status info (stop number, segment, days remaining, leg badge) moves into header subtitle. Cleaner, less visual noise.

#### 3c. Built Stops → Panel Card
**Current:** Flat list with h3 "Ausgewählte Stops".
**New:** `acc-stop-panel`-style container:
```html
<div class="route-panel">
  <div class="route-panel-header">
    <h3>Ausgewählte Stops</h3>
    <span class="badge">{count} von {total} Stops</span>
  </div>
  <div class="route-panel-body">
    {built stops list — keep current compact format}
  </div>
</div>
```

#### 3d. Options Container → Panel Card
**Current:** Bare `.options-grid` div.
**New:** Wrapped in panel:
```html
<div class="route-panel">
  <div class="route-panel-header">
    <h3>Verfügbare Optionen</h3>
    <span class="badge">{count} Optionen</span>
  </div>
  <div class="route-panel-body">
    <div class="options-grid">{option cards}</div>
  </div>
</div>
```

#### 3e. Recompute Bar → Inside Options Panel Header
Move the recompute input+button into the options panel header area, so it's contextually grouped.

#### 3f. Region-Plan → Panel Card
```html
<div class="route-panel">
  <div class="route-panel-header">
    <h3>Regionen-Plan</h3>
    <div class="region-actions">
      <button class="btn btn-secondary btn-sm">Neu berechnen</button>
      <button class="btn btn-primary btn-sm">Route bestätigen</button>
    </div>
  </div>
  <div class="route-panel-body">
    <p class="region-summary">{summary}</p>
    <div class="region-plan-layout">
      <div class="region-cards-list">{region cards}</div>
      <div class="region-map-panel">{map}</div>
    </div>
  </div>
</div>
```

#### 3g. No-Stops-Found → Styled Card
Replace inline-styled div with proper card using design system classes.

---

## New CSS Classes

```
/* Unified photo */
.hero-photo, .hero-photo--lg, .hero-photo--md, .hero-photo--sm
.hero-photo-count, .hero-photo-loading, .hero-photo-shimmer

/* Route builder panels */
.route-panel, .route-panel-header, .route-panel-body
.route-builder-subtitle

/* Region cards */
.region-card, .region-card-body, .region-card-header
.region-card-number, .region-teaser, .region-highlights
.region-reason, .region-drag-handle
.region-cards-list, .region-plan-layout, .region-map-panel
.region-summary, .region-actions
.region-replace-form

/* No stops found */
.no-stops-card
```

---

## Files Changed

| File | Changes |
|------|---------|
| `frontend/js/state.js` | Add `buildHeroPhoto()`, deprecate `buildPhotoGallery()` |
| `frontend/js/route-builder.js` | Rewrite `showRegionPlanUI()`, `renderOptions()`, `renderBuiltStops()`, `_buildOptionCardHTML()`, `_showNoStopsFoundUI()`; use hero-photo; add panel wrappers |
| `frontend/js/accommodation.js` | Replace photo-strip with hero-photo in `renderAccCards()` |
| `frontend/js/guide.js` | Replace photo-strip with hero-photo in all render functions; update `_lazyLoadEntityImages()` |
| `frontend/styles.css` | Add hero-photo, route-panel, region-card classes; update acc-option-card layout; remove deprecated photo-strip styles |
| `frontend/index.html` | Update route-builder section structure (panels, remove bare route-status div) |
| `backend/models/trip_leg.py` | Add `teaser`, `highlights` to `RegionPlanItem` |
| `backend/agents/region_planner.py` | Update `REGION_SCHEMA` and prompt |

---

## Testing

- All existing tests remain valid (no API contract changes, only additive model fields)
- Backend: `RegionPlanItem` new fields have defaults → backward compatible
- Frontend: Visual testing in browser — verify all photo locations render hero-photo correctly
- Verify lightbox works from hero-photo click in all locations
- Verify region cards load images via Google Places API
- Verify drag-and-drop still works with new region card layout
