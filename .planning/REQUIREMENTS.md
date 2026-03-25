# Requirements: Travelman3

**Defined:** 2026-03-25
**Core Value:** Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### AI Quality

- [x] **AIQ-01**: StopOptionsFinder uses correct production model (claude-sonnet-4-5) instead of hardcoded claude-haiku-4-5
- [x] **AIQ-02**: All geocoded stop coordinates are validated against the route corridor bounding box before being accepted
- [x] **AIQ-03**: Stop finder prompts enforce the user's travel style preference (beach, ocean, mountains, culture) so suggestions match the trip theme
- [x] **AIQ-04**: Stop suggestions maintain consistent quality — no random low-effort entries mixed with good ones
- [x] **AIQ-05**: Route architect produces driving-efficient routes without unnecessary zigzag or backtracking

### Geographic Routing

- [ ] **GEO-01**: Route planning handles island destinations by identifying ferry crossings and port cities
- [x] **GEO-02**: Stop finder resolves coordinates to actual island locations, not nearby mainland points
- [x] **GEO-03**: System detects when Google Directions returns no route (0,0 fallback) and attempts ferry-aware alternatives
- [x] **GEO-04**: Common island groups (Greek islands, Corsica, Sardinia, Balearics) have ferry-port awareness
- [ ] **GEO-05**: Route planning accounts for ferry time in daily driving budget

### User Route Control

- [ ] **CTL-01**: User can remove a stop from the proposed route
- [ ] **CTL-02**: User can add a custom stop to the route at any position
- [ ] **CTL-03**: User can reorder stops in the route sequence via drag-and-drop
- [ ] **CTL-04**: User can replace a stop with guided "find something else" flow (e.g., "more beach", "less driving")
- [ ] **CTL-05**: Route metrics (total distance, driving time, budget) update after any route modification

### UI Redesign

- [ ] **UIR-01**: Desktop layout uses map-centric split-panel with map as the hero element
- [ ] **UIR-02**: Layout is fully responsive — comfortable to use on phone browsers
- [ ] **UIR-03**: Stops are presented as visual cards with photos, key facts, and travel style tags
- [ ] **UIR-04**: Day-by-day timeline is interactive — scrollable with expandable day details
- [ ] **UIR-05**: Dashboard overview shows key trip stats (total days, stops, distance, budget remaining)
- [ ] **UIR-06**: Map and content panels stay synchronized — selecting a stop highlights it on the map and vice versa

### Sharing

- [ ] **SHR-01**: User can generate a public shareable link for any saved trip plan
- [ ] **SHR-02**: Shared link shows a read-only view of the full trip plan (no authentication required)
- [ ] **SHR-03**: User can revoke (disable) a previously shared link
- [ ] **SHR-04**: PDF/PPTX export functionality is removed from the codebase

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced User Control

- **CTL-06**: User can adjust preferences (pace, budget, style) mid-planning and regenerate affected stops
- **CTL-07**: Dashboard overview with trip analytics (cost breakdown charts, distance graphs)

### Enhanced Sharing

- **SHR-05**: Shared trip includes interactive map (not just static view)
- **SHR-06**: Share link includes social media preview card (Open Graph meta tags)

### Quality

- **AIQ-06**: Stop quality scoring with automated validation against Google Places API
- **AIQ-07**: A/B testing framework for prompt variants to measure stop quality over time

## Out of Scope

| Feature | Reason |
|---------|--------|
| Native mobile app | Responsive web sufficient for friends & family audience |
| PWA/offline support | Not needed for current user base |
| OAuth/social login | Email/password sufficient |
| Real-time collaborative editing | Single-user planning flow |
| Monetization/payments | Personal project |
| Multi-language support | German-only as designed |
| CSS framework migration | Vanilla CSS with Grid/Container Queries is sufficient |
| Map library migration | Current Google Maps SDK + Leaflet covers all needs |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AIQ-01 | Phase 1 | Complete |
| AIQ-02 | Phase 1 | Complete |
| AIQ-03 | Phase 1 | Complete |
| AIQ-04 | Phase 1 | Complete |
| AIQ-05 | Phase 1 | Complete |
| GEO-01 | Phase 2 | Pending |
| GEO-02 | Phase 2 | Complete |
| GEO-03 | Phase 2 | Complete |
| GEO-04 | Phase 2 | Complete |
| GEO-05 | Phase 2 | Pending |
| CTL-01 | Phase 3 | Pending |
| CTL-02 | Phase 3 | Pending |
| CTL-03 | Phase 3 | Pending |
| CTL-04 | Phase 3 | Pending |
| CTL-05 | Phase 3 | Pending |
| UIR-01 | Phase 4 | Pending |
| UIR-02 | Phase 4 | Pending |
| UIR-03 | Phase 4 | Pending |
| UIR-04 | Phase 4 | Pending |
| UIR-05 | Phase 4 | Pending |
| UIR-06 | Phase 4 | Pending |
| SHR-01 | Phase 5 | Pending |
| SHR-02 | Phase 5 | Pending |
| SHR-03 | Phase 5 | Pending |
| SHR-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-25 after roadmap creation*
