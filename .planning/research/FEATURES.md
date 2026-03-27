# Feature Landscape

**Domain:** Progressive disclosure travel view redesign for AI road trip planner
**Researched:** 2026-03-27
**Confidence:** HIGH (based on existing codebase analysis, competitive travel app patterns, and progressive disclosure UX research)

## Table Stakes

Features users expect from a drill-down travel view. Missing = the redesign feels broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Overview showing all stops on map + summary stats | First thing users want is "what's my whole trip look like" — already exists | Low | Existing `renderOverview()` and `fitAllStops()` cover this. Needs compact day cards added. |
| Day drill-down with map zoom to day region | Wanderlog, Google Travel, and every serious trip planner scopes the map when you click a day | Medium | No `fitBoundsForDay()` exists yet. Need to build bounds from `_findStopsForDay()` coordinates + drive waypoints. |
| Stop drill-down with map zoom to stop | Clicking a stop should pan/zoom map to that stop's location — users expect this from any map-centric app | Low | `panToStop()` already exists. Need to also zoom in (currently only pans). |
| Breadcrumb navigation (Overview > Day 3 > Stop: Annecy) | Progressive disclosure requires knowing where you are and how to get back | Low | Currently exists partially — day detail has "Alle Tage" back button. Need consistent breadcrumb across all levels. |
| Collapse unfocused content when drilling down | Core progressive disclosure principle — showing everything defeats the purpose | Medium | Days tab already collapses other days. Need same pattern for overview-to-day and day-to-stop transitions. |
| Animated map transitions between views | Jarring map jumps feel broken. `panTo()` with smooth animation is expected. | Low | Google Maps `panTo()` already animates. `fitBounds()` with padding animates too. Just need to call them at the right times. |
| Back button / browser history for drill-down | Users expect browser back to go up one level, not leave the page entirely | Medium | Router already handles tab-level URLs (`/travel/{id}/stops`). Need sub-routes for day and stop drill-down (`/travel/{id}/day/3`, `/travel/{id}/stop/5`). |
| Responsive drill-down (mobile: map collapses or goes full-width above content) | Current responsive layout already handles split panel. Drill-down must not break mobile. | Low | Existing container queries handle panel sizing. Map focus changes work regardless of panel size. |

## Differentiators

Features that set this apart from "just another tab view." Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Day-scoped route polyline | When drilling into Day 3, show only that day's route segment highlighted, dim the rest | Medium | Currently `_guidePolyline` is one full polyline. Need to segment by day or overlay a highlighted segment. Requires route geometry per day (available from `day_plans[].time_blocks` drive segments). |
| Day card mini-summaries on overview | Compact day cards showing "Day 1: Liestal to Annecy -- 3.5h drive, 2 activities" without expanding | Low | Data already available. Just a new render function combining `_findStopsForDay()` output into compact cards. |
| Stop-to-stop transition animation | When navigating between stops, animate the map along the route polyline | High | Impressive but expensive. Google Maps doesn't provide built-in route animation. Would need manual `panTo()` steps along decoded polyline. Defer. |
| Smart map padding for content panel | When content panel overlaps map (mobile/tablet), adjust map bounds padding so focused area isn't hidden behind content | Low | `fitBounds()` accepts padding parameter `{top, right, bottom, left}`. Calculate from content panel width. |
| Contextual marker styling per drill-down level | Overview: all markers same style. Day view: day's stops are large/colored, others are small/gray. Stop view: focused stop is large, others are dots. | Medium | Requires updating `_guideMarkerList` icons dynamically. Google Maps `Marker.setIcon()` supports this. |
| Day weather/drive summary badges | Show weather icon and total drive time as badges on day cards | Low | Weather data may already be in day plans. Drive time is calculable from time blocks. |
| Keyboard navigation between days/stops | Arrow keys or j/k to move between days in day view, stops in stop view | Low | Simple keydown listener. Good accessibility. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Separate page/URL per stop with full page reload | Kills the fluidity of drill-down. Travel apps that navigate away from the map lose context. | Keep everything in the split-panel layout. Drill-down updates content panel + map bounds, never navigates away. |
| 3D map fly-through between stops | Cool demo, terrible UX. Disorienting, slow, can't skip. Google Earth API is heavy. | Smooth 2D `fitBounds()` transitions are sufficient and fast. |
| Collapsible map panel | Users might collapse the map and lose the core value of the app. Map is always visible. | Map stays fixed. Content panel scrolls. On mobile, map is above content (already works). |
| Nested tabs within drill-down | Tabs inside tabs inside tabs = cognitive overload. Overview > Days tab > Day 3 > Activities tab > ... | Use flat content sections within each drill-down level. Day view shows time blocks, activities, restaurants in one scrollable view. |
| Automatic drill-down on page load | Don't auto-drill into Day 1 when opening a trip. Users want the overview first. | Always start at overview level. Let user choose where to drill. |
| Custom map styles per travel style | Tempting to show "adventure" trips on terrain map, "cultural" on satellite. Adds complexity, low value. | Use standard road map for all trips. Focus on marker and polyline styling instead. |

## Feature Dependencies

```
Overview compact day cards → Day drill-down (cards are the entry point to day view)
Day drill-down → fitBoundsForDay() map function (new)
Day drill-down → Day-scoped route polyline (differentiator, but strongly coupled)
Stop drill-down → panToStop() with zoom (minor enhancement to existing)
Breadcrumb navigation → Router sub-routes for day/stop levels
Contextual marker styling → Day drill-down (markers change per level)
Browser history → Router sub-routes (prerequisite)
```

## Drill-Down Behavior Specification

Based on research of Wanderlog, Google Travel, and progressive disclosure best practices:

### Level 1: Overview (default)
- **Map:** `fitAllStops()` — entire route visible, all markers shown equally
- **Content:** Summary stats, compact route line, compact day cards (clickable), trip analysis
- **Markers:** All stops shown with standard numbered markers
- **Polyline:** Full route shown

### Level 2: Day View
- **Map:** `fitBoundsForDay(dayNum)` — zoom to bounding box of that day's stops + route with padding
- **Content:** Day title, description, time blocks (schedule), stops visited that day, activities, restaurants
- **Markers:** Day's stops are full-size colored markers; other stops are small gray dots
- **Polyline:** Full route dimmed (opacity 0.2), day's segment highlighted (opacity 1.0, thicker)
- **Navigation:** Breadcrumb "Uebersicht > Tag 3", prev/next day buttons, back to overview
- **Entry:** Click day card on overview, click day in sidebar, URL `/travel/{id}/day/{n}`

### Level 3: Stop View
- **Map:** `panToStop()` + zoom to ~13 — centered on stop, show nearby POIs
- **Content:** Stop name, region, accommodation, activities grid, restaurants list, travel guide excerpt
- **Markers:** Focused stop is large with label; other day stops are medium; rest are tiny dots
- **Polyline:** Route segments to/from this stop highlighted
- **Navigation:** Breadcrumb "Uebersicht > Tag 3 > Annecy", prev/next stop buttons, back to day
- **Entry:** Click stop card in day view, click marker on map, URL `/travel/{id}/stop/{id}`

### Map Focus Patterns (from competitive analysis)

| Pattern | Used By | Implementation |
|---------|---------|---------------|
| fitBounds to day's stops | Wanderlog, Google Travel | `LatLngBounds` from day's stop coords, `map.fitBounds(bounds, padding)` |
| Dim non-focused markers | Airbnb, Google Maps, Wanderlog | `marker.setIcon()` to gray/small, or `marker.setOpacity(0.3)` |
| Highlighted route segment | Google Directions, Citymapper | Second polyline overlay on top with bolder style; or modify `strokeOpacity` array |
| Padding for content panel | Google Maps, Apple Maps | `fitBounds({padding: {left: contentPanelWidth}})` |
| Smooth pan+zoom transition | All map-centric apps | Google Maps API handles this natively with `panTo()` and `fitBounds()` |

## MVP Recommendation

**Phase 1 — Core drill-down (table stakes):**
1. Compact day cards on overview (entry point for day drill-down)
2. `fitBoundsForDay()` map function
3. Day drill-down view with map zoom
4. Stop drill-down view with map zoom (enhance existing `panToStop`)
5. Breadcrumb navigation across all 3 levels
6. Router sub-routes for day/stop levels (browser history)

**Phase 2 — Polish (differentiators):**
7. Contextual marker styling (focused vs dimmed)
8. Day-scoped route polyline highlighting
9. Smart map padding for content panel overlap
10. Keyboard navigation (j/k between days/stops)

**Defer:**
- Stop-to-stop route animation: High complexity, low user value
- 3D/fly-through: Anti-feature territory
- Day weather badges: Nice but needs weather API data pipeline

## Existing Code to Leverage

| Existing | Reuse For |
|----------|-----------|
| `_findStopsForDay(plan, dayNum)` | Get stop coordinates for day bounds calculation |
| `GoogleMaps.panToStop(stopId, stops)` | Stop-level map focus (needs zoom addition) |
| `GoogleMaps.fitAllStops(plan)` | Template for `fitBoundsForDay()` — same pattern, filtered stops |
| `renderDaysOverview(plan)` accordion pattern | Day card click → drill-down trigger |
| `renderDayDetail(plan, dayNum)` | Already exists — needs map integration, breadcrumb, URL support |
| `renderStopDetail(plan, stopId)` | Already exists — needs breadcrumb, back-to-day navigation |
| `_updateMapForTab(plan, tab)` | Extend to handle drill-down level, not just tab |
| Router pattern matching | Add `/travel/{id}/day/{n}` and `/travel/{id}/stop/{id}` routes |
| `_guidePolyline` | Segment or overlay for day-scoped highlighting |
| `highlightGuideMarker(stopId)` | Extend for multi-marker contextual styling |

## Sources

- [Progressive Disclosure - Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/)
- [Progressive disclosure in UX design - LogRocket](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)
- [Wanderlog - Hide lists or days on map](https://help.wanderlog.com/hc/en-us/articles/5159543865499-Hide-lists-or-days-on-map)
- [Wanderlog - Itinerary compact view](https://help.wanderlog.com/hc/en-us/articles/13356092870427-Itinerary-compact-view)
- [Google Maps JS API fitBounds pattern](https://gist.github.com/mbeaty/1261182)
- Codebase analysis: `frontend/js/guide.js`, `frontend/js/maps.js`
