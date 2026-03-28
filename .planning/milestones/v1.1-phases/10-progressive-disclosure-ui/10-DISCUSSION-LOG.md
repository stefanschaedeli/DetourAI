# Phase 10: Progressive Disclosure UI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 10-progressive-disclosure-ui
**Areas discussed:** Overview landing, Drill-down transitions, Breadcrumb & back-nav

---

## Overview Landing

### Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Compact day cards | Trip summary header + grid of clickable day cards (day number, title, stop count, drive time) | ✓ |
| Summary + day list | Keep current overview content at top, scrollable day list below | |
| Dashboard cards | Stats widgets at top + day cards below | |

**User's choice:** Compact day cards
**Notes:** Current detailed overview content moves out of the primary view

### Existing Content Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Move into day drill-down | Budget/analysis/prose move to drill-down levels, overview stays clean | |
| Collapsible section below cards | Keep content below day cards grid, collapsed by default | ✓ |
| Separate 'Details' tab | Tab/toggle between day-cards view and full overview content | |

**User's choice:** Collapsible section below cards
**Notes:** User wants trip analysis accessible at overview level without extra drill-down clicks

### Day Card Thumbnails

| Option | Description | Selected |
|--------|-------------|----------|
| No thumbnails | Text-only cards, compact and fast-loading | |
| Small thumbnail | First stop's photo on each card | ✓ |

**User's choice:** Small thumbnail
**Notes:** Visual richness preferred over minimal cards

---

## Drill-Down Transitions

### Transition Style

| Option | Description | Selected |
|--------|-------------|----------|
| Instant swap | Content replaces immediately, no animation | |
| Slide left/right | Directional slide animation | |
| Crossfade | Current content fades out, new fades in | ✓ |

**User's choice:** Crossfade
**Notes:** Polished feel preferred, CSS transitions with JS coordination

### Scroll Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Always scroll to top | Every drill-down resets scroll position | ✓ |
| Stay at current position | Keep scroll position on navigation | |

**User's choice:** Always scroll to top

### Map Animation

| Option | Description | Selected |
|--------|-------------|----------|
| Smooth pan+zoom | Google Maps panTo/fitBounds with animation | ✓ |
| Instant jump | Map snaps to new bounds immediately | |

**User's choice:** Smooth pan+zoom
**Notes:** Already supported natively by Google Maps API

---

## Breadcrumb & Back-Nav

### Breadcrumb Design

| Option | Description | Selected |
|--------|-------------|----------|
| Unified top bar | Persistent bar: Uebersicht > Tag 3 > Annecy, each segment clickable | ✓ |
| Back button only | Just back arrow + parent label, one level up | |
| Inline breadcrumb per view | Keep existing breadcrumb spans within detail views | |

**User's choice:** Unified top bar
**Notes:** Hidden at overview level, shows path at day and stop levels

### URL Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Push URL state | Each drill-down pushes URL (/travel/42/day/3, /travel/42/stop/5), browser back works | ✓ |
| No URL changes | Drill-down is purely in-page | |

**User's choice:** Push URL state
**Notes:** Extends existing router.js patterns

---

## Claude's Discretion

- Map focus/dimming behavior at each drill level (not discussed, left to Claude)
- Crossfade timing and easing
- Day card grid responsive layout
- Thumbnail fallbacks
- Marker dimming approach
- Collapsible section toggle design
- Edit UI integration at drill levels

## Deferred Ideas

None — discussion stayed within phase scope
