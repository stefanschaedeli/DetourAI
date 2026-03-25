# Feature Landscape

**Domain:** AI-powered road trip planner (stabilization + UX redesign)
**Researched:** 2026-03-25
**Confidence:** MEDIUM (based on competitive analysis of Wanderlog, Furkot, Roadtrippers, Google Travel, Tripsy, and AI planner trend reports)

---

## Table Stakes

Features users expect from any travel planning tool in 2025-2026. Missing = product feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Map as hero element** | Every competitor (Wanderlog, Furkot, Roadtrippers, Google Travel) centers the map. Users orient spatially first, details second. | High | Current app has map but it's secondary. Needs split-panel layout: map left/top, content right/bottom. |
| **Drag-and-drop stop reordering** | Furkot and Wanderlog both support it. Users who pick stops expect to rearrange them freely. | Medium | Requires backend route recalculation on reorder. Frontend: HTML5 drag API or pointer events. |
| **Stop add/remove/edit** | Basic CRUD on stops. Furkot, Roadtrippers, and Wanderlog all allow manual stop insertion and deletion at any point. | Medium | Existing "replace stop" flow is a start. Need: add arbitrary stop, delete stop, rename stop. |
| **Mobile-responsive layout** | 60%+ of travel research happens on mobile. Any app without mobile support loses the "on the road" use case entirely. | High | Current design is desktop-only. Need mobile-first redesign with bottom sheets, collapsible panels, and touch-friendly tap targets. |
| **Consistent AI output quality** | CNBC (March 2026) reports hallucinations remain the #1 trust killer for AI travel planners. GuideGeek targets 98% accuracy via human-in-the-loop. | High | Current app has inconsistent stop quality, mainland-biased coordinates, and travel-style drift. This is the core product quality issue. |
| **Photo-rich stop cards** | Google Travel, Wanderlog, and Airbnb all use large imagery for destinations. Text-only stop lists feel outdated. | Medium | Already have image_fetcher.py. Need: larger hero images per stop, fallback handling, lazy loading. |
| **Real-time progress feedback** | Already exists (SSE streaming). Table stakes because AI planning takes 30-120 seconds. Users need visible progress or they abandon. | Low | Existing. Polish the overlay and skeleton states. |
| **Save and reload trips** | Already exists. Every competitor offers this. | Low | Existing. No changes needed. |
| **Budget overview dashboard** | Users need to see where money goes at a glance. Current budget tracking exists but is buried in results. | Medium | Surface the 45/15/fuel/activities split as a visual dashboard element (pie chart or bar segments). |

---

## Differentiators

Features that set the product apart. Not expected, but valued. These create competitive advantage over generic ChatGPT itineraries.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Shareable trip links (public, read-only)** | Friends/family can view the full trip plan without accounts. Replaces PDF/PPTX export with something better. No competitor does this as cleanly for road trips specifically. | Medium | New endpoint: `/api/trips/{share_id}/public`. Generate UUID-based share tokens. Render a read-only version of the guide view. |
| **Interactive route building (pick-your-stops)** | Most AI planners generate a fixed itinerary. Travelman3's "choose from 3 options per leg" is genuinely unique. Polish this into a first-class UX. | Low | Already exists. Improve card design, add map highlighting on hover, animate transitions between legs. |
| **Region/explore mode** | Let AI suggest a cluster of stops for an area rather than a single point. Competitors don't do this -- they treat every stop as a point, not an area. | Low | Already exists. Surface it more prominently, improve the UI. |
| **Day-by-day timeline with expandable details** | A scrollable, visual day-planner (morning/afternoon/evening blocks) with driving segments. More structured than competitors' flat lists. | Medium | Current guide.js has tab-based rendering. Redesign as a vertical timeline with expandable cards per activity. |
| **Mid-trip preference adjustment** | "I want more beach stops" or "switch from culture to food focus" partway through planning. Re-generate only affected legs. | High | Partially exists via stop replacement. Full implementation means: change travel style mid-route and re-run affected agents. |
| **Weather-aware scheduling** | Show forecast data for each stop's dates. Already have weather.py utility. Surface it in the day planner. | Low | Utility exists. Need: weather icons in day cards, "bring rain gear" hints. |
| **Driving segment visualization** | Show each drive segment with duration, distance, and notable waypoints on the map. Furkot does this well. | Medium | Google Directions data already fetched. Render polylines per segment with info windows. |
| **Stop quality scoring (internal)** | Rate AI-generated stops on relevance, geographic accuracy, and style-match. Log scores. Use to improve prompts over time. | Medium | New backend utility. Score each stop option against: correct coordinates (Google geocode verify), style match, uniqueness. Enables quality monitoring. |

---

## Anti-Features

Features to explicitly NOT build. Each was considered and rejected for good reason.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **PDF/PPTX export** | Maintenance burden for a feature nobody uses. Share links are superior. | Remove output_generator.py entirely. Implement shareable web links. |
| **Real-time collaborative editing** | PROJECT.md explicitly scopes this out. Friends & family audience doesn't need Google Docs-style co-editing. Massive complexity (WebSocket sync, conflict resolution). | Single-user planning + read-only share links cover the use case. |
| **Native mobile app** | Not justified for the audience size. Responsive web covers mobile needs. | Invest in excellent responsive design instead. |
| **Social login (Google/Facebook OAuth)** | Adds complexity, privacy concerns, and dependency on third-party auth. Current JWT system works for the audience. | Keep email/password auth. |
| **Booking integration** | Connecting to Booking.com/Airbnb APIs is a legal/commercial minefield. Breaks constantly. Not needed for planning. | Show accommodation suggestions with external links. Let users book separately. |
| **Gamification / achievement badges** | Trivializes the travel planning experience. Doesn't fit the Apple-inspired design philosophy. | Focus on beautiful, functional design that creates emotional engagement through imagery and typography. |
| **Multi-language support** | German-only by design. Translation effort not justified for friends & family. | Keep all text in German. |
| **Offline/PWA mode** | Adds service worker complexity. Users plan trips with internet access. | Not needed for current audience. |
| **AI chat interface** | "Talk to your trip planner" is trendy but worse UX than structured forms + guided selection. Chat requires more user effort for worse results. | Keep the structured 5-step form + interactive route builder. More opinionated = better results. |

---

## Feature Dependencies

```
Map-centric layout ──────────── required before ──→ Driving segment visualization
                   └──────────── required before ──→ Drag-and-drop stop reordering (map updates)

Mobile-responsive layout ────── required before ──→ Shareable trip links (recipients view on mobile)

Stop add/remove/edit ────────── required before ──→ Mid-trip preference adjustment

Photo-rich stop cards ───────── required before ──→ Day-by-day timeline redesign

AI quality improvements ─────── independent (can run in parallel with UX work)

Shareable trip links ────────── requires: public API endpoint + read-only guide renderer

Budget dashboard ────────────── requires: existing budget data (already available)

Weather integration ─────────── requires: existing weather.py (already available)
```

---

## MVP Recommendation

**Phase 1 priorities (foundation):**

1. **AI quality improvements** -- Fix geographic accuracy, travel-style adherence, and stop consistency. This is the core product. A beautiful UI showing wrong destinations is useless.
2. **Map-centric layout redesign** -- Split-panel: map on left (desktop) or top (mobile), content on right/bottom. Every interaction highlights on map.
3. **Mobile-responsive layout** -- Mobile-first CSS with bottom sheets for stop details, collapsible panels, touch-friendly interactions.

**Phase 2 priorities (interaction):**

4. **Drag-and-drop stop reordering** -- With automatic route recalculation.
5. **Stop add/remove** -- Manual stop insertion and deletion.
6. **Photo-rich stop cards** -- Large images, lazy loading, fallback to placeholder.

**Phase 3 priorities (sharing + polish):**

7. **Shareable trip links** -- Public read-only view with unique URLs.
8. **Day-by-day timeline** -- Expandable vertical timeline with driving segments.
9. **Budget dashboard** -- Visual cost breakdown.
10. **Weather integration** -- Surface existing data in the UI.

**Defer:**
- Mid-trip preference adjustment: High complexity, low urgency. Existing stop replacement covers 80% of the need.
- Stop quality scoring (internal): Valuable for long-term quality but not user-facing. Build after AI quality is stabilized.

---

## Current State vs Target

| Area | Current | Target |
|------|---------|--------|
| Map role | Secondary, alongside content | Hero element, always visible, interactive |
| Stop editing | Replace only (full re-research) | Add, remove, reorder, rename, replace |
| Mobile support | None (desktop-only) | Full responsive, bottom-sheet patterns |
| Trip sharing | PDF/PPTX export (deprecated) | Public shareable web links |
| AI consistency | Inconsistent (island/coastal issues, style drift) | Validated coordinates, style-adherent, scored |
| Stop presentation | Text-heavy with small images | Card-based with hero photos (Airbnb-style) |
| Day planning | Tab-based flat view | Scrollable vertical timeline with expandable blocks |
| Budget visibility | Buried in results | Dashboard with visual breakdown |

---

## Sources

- [CNBC: AI travel planners growing but hallucinations persist (March 2026)](https://www.cnbc.com/2026/03/11/ai-travel-planners-tourism-popularity-trust-hallucinations.html)
- [Furkot: Drag-and-drop stop reordering](https://help.furkot.com/how-to/reorder-stops.html)
- [Furkot: Route dragging features](https://help.furkot.com/features/dragging-routes.html)
- [Wanderlog: Collaborative travel planning](https://wanderlog.com/)
- [Google: AI-powered travel planning in Search, Maps, Gemini](https://techcrunch.com/2025/03/27/google-rolls-out-new-vacation-planning-features-to-search-maps-and-gemini/)
- [TravelTime: Interactive map design and UX examples](https://traveltime.com/blog/interactive-map-design-ux-mobile-desktop)
- [AppInventiv: AI trip planner development guide](https://appinventiv.com/blog/build-ai-trip-planner-app/)
- [Map UI Patterns](https://mapuipatterns.com/)
- [Wanderlog vs Tripsy comparison](https://www.wandrly.app/comparisons/wanderlog-vs-tripsy)
- [Travo: Best AI trip planner 2025](https://travo.me/blog/best-ai-trip-planner-app-2025)
