# Requirements: DetourAI

**Defined:** 2026-03-27
**Core Value:** Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type — mainland, coastal, and island regions alike.

## v1.1 Requirements

Requirements for v1.1 Polish & Travel View Redesign. Each maps to roadmap phases.

### Tech Debt

- [ ] **DEBT-01**: Celery include list registers `replace_stop_job` so stop replacement works in production
- [ ] **DEBT-02**: Map markers and polyline refresh after route edits (add/remove/reorder/replace stops)
- [ ] **DEBT-03**: Stats bar updates immediately after route edits instead of lagging by one edit cycle
- [ ] **DEBT-04**: RouteArchitect respects `max_drive_time_per_day` constraint and avoids overlong driving days with ferries/islands

### Code Structure

- [ ] **STRC-01**: guide.js split into focused modules (overview, day-detail, stop-detail, map-focus, shared utils) with zero behavioral changes

### Navigation

- [ ] **NAV-01**: Travel view shows compact overview with trip summary, day cards, and full-route map as default landing
- [ ] **NAV-02**: User can drill into a day to see that day's stops, activities, restaurants with map focused on day's region
- [ ] **NAV-03**: User can drill into a stop to see accommodation, activities, restaurants with map focused on stop area
- [ ] **NAV-04**: Breadcrumb navigation allows back-navigation at each drill level (overview <- day <- stop)
- [ ] **NAV-05**: Map markers dim for non-focused stops when viewing a specific day or stop
- [ ] **NAV-06**: Browser back/forward buttons work with drill-down navigation via URL routing

### Verification

- [ ] **VRFY-01**: 9 pending UI items from v1.0 verified in browser and fixed if broken

## Future Requirements

### Polish

- **PLSH-01**: Day-scoped polyline highlighting (bold current day's route, dim rest)
- **PLSH-02**: Keyboard navigation through drill-down levels
- **PLSH-03**: View Transitions API for smooth cross-fade animations
- **PLSH-04**: Smart map padding when content panel overlaps map on mobile

## Out of Scope

| Feature | Reason |
|---------|--------|
| Framework migration (React/Vue/Svelte) | Vanilla JS is working well, no justification for migration overhead |
| Complete guide.js rewrite | Module split with zero behavioral changes is safer and sufficient |
| Mobile native app | Responsive web covers the friends & family audience |
| Offline/PWA support | Not needed for current user base |
| Real-time collaborative trip editing | Single-user planning is sufficient |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 8 | Pending |
| DEBT-02 | Phase 8 | Pending |
| DEBT-03 | Phase 8 | Pending |
| DEBT-04 | Phase 8 | Pending |
| STRC-01 | Phase 9 | Pending |
| NAV-01 | Phase 10 | Pending |
| NAV-02 | Phase 10 | Pending |
| NAV-03 | Phase 10 | Pending |
| NAV-04 | Phase 10 | Pending |
| NAV-05 | Phase 10 | Pending |
| NAV-06 | Phase 10 | Pending |
| VRFY-01 | Phase 11 | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after roadmap creation*
