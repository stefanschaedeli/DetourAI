# Roadmap: DetourAI

## Milestones

- ✅ **v1.0 AI Trip Planner MVP** — Phases 1-7 (shipped 2026-03-26) — [Archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish & Travel View Redesign** — Phases 8-11 (shipped 2026-03-28) — [Archive](milestones/v1.1-ROADMAP.md)
- 🚧 **v1.2 AI-Qualität & Routenplanung** — Phases 12-16 (in progress)

## Phases

<details>
<summary>✅ v1.0 AI Trip Planner MVP (Phases 1-7) — SHIPPED 2026-03-26</summary>

- [x] Phase 1: AI Quality Stabilization (3/3 plans) — AI model fix, corridor validation, style enforcement, quality gating
- [x] Phase 2: Geographic Routing (2/2 plans) — Island-aware routing, ferry detection, port awareness
- [x] Phase 3: Route Editing (3/3 plans) — Remove/add/reorder/replace stops with Celery tasks
- [x] Phase 4: Map-Centric Responsive Layout (6/6 plans) — Split-panel map-hero, stop cards, day timeline, mobile responsive
- [x] Phase 5: Sharing & Cleanup (3/3 plans) — Public shareable links, PDF/PPTX export removal
- [x] Phase 6: Wiring Fixes (2/2 plans) — Share token persistence, tags, SSE events, hints
- [x] Phase 7: Ferry-Aware Route Edits (1/1 plans) — Ferry-aware directions in all edit paths

**25/25 requirements satisfied** | **286 tests passing** | **166 commits**

</details>

<details>
<summary>✅ v1.1 Polish & Travel View Redesign (Phases 8-11) — SHIPPED 2026-03-28</summary>

- [x] Phase 8: Tech Debt Stabilization (2/2 plans) — Celery fix, map redraw, stats bar, drive limits
- [x] Phase 9: Guide Module Split (2/2 plans) — guide.js split into 7 focused modules
- [x] Phase 10: Progressive Disclosure UI (3/3 plans) — Three-level drill-down with breadcrumb and map focus
- [x] Phase 11: Browser Verification (4/4 plans) — 18 UI items verified, 7 gaps fixed

**12/12 requirements satisfied** | **291 tests passing** | **34 commits**

</details>

### 🚧 v1.2 AI-Qualität & Routenplanung (In Progress)

**Milestone Goal:** Die AI-gesteuerte Routenplanung und Stop-Auswahl grundlegend verbessern — intelligentere Tagesverteilung, bessere Kontextweiterleitung, und UI-Korrekturen für eine nutzbare Reiseplanung.

- [ ] **Phase 12: Context Infrastructure + Wishes Forwarding** — Globales Wunschfeld im Formular; alle 9 Agents erhalten travel_description, preferred_activities, mandatory_activities
- [ ] **Phase 13: Architect Pre-Plan for Interactive Flow** — Lightweight Sonnet pre-plan vor StopOptionsFinder; Regionen und Nächte-Empfehlungen in job state
- [ ] **Phase 14: Stop History Awareness + Night Distribution** — StopOptionsFinder kennt alle bisherigen Stops; Nächte-Verteilung nach Ort-Potenzial; Dedup-Safety-Net
- [ ] **Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation** — Haversine-Validierung für Geheimtipps; Tagesplan-Neuberechnung nach Nächte-Änderungen
- [ ] **Phase 16: Frontend UI Fixes + Polish** — Karte auf Route fokussiert, korrekte Stop-Bilder, Tooltips, Stop-Auswahl-Karte mit History

## Phase Details

### Phase 12: Context Infrastructure + Wishes Forwarding
**Goal**: Nutzerwünsche (Aktivitäten, Reisestil, Pflichtaktivitäten) erreichen alle 9 Agents zuverlässig
**Depends on**: Phase 11
**Requirements**: CTX-01, CTX-02, CTX-03
**Success Criteria** (what must be TRUE):
  1. User kann im Formular einen Freitext für globale Aktivitätswünsche eingeben
  2. Eingegebene Wünsche erscheinen im Prompt aller 9 Agents (verifizierbar per Logs)
  3. mandatory_activities sind in StopOptionsFinder- und ActivitiesAgent-Prompts sichtbar
  4. Wenn kein Wunschtext eingegeben wird, funktionieren alle Agents weiterhin unverändert
**Plans:** 1/2 plans executed
Plans:
- [x] 12-01-PLAN.md — Frontend UI: preferred_activities tag input + travel_description placeholder
- [ ] 12-02-PLAN.md — Backend: wishes context in all 8 agent prompts + test coverage

### Phase 13: Architect Pre-Plan for Interactive Flow
**Goal**: StopOptionsFinder erhält Regions- und Nächtekontext vom Architect vor der ersten Stop-Auswahl
**Depends on**: Phase 12
**Requirements**: RTE-01, RTE-02, RTE-05
**Success Criteria** (what must be TRUE):
  1. Vor dem ersten StopOptionsFinder-Aufruf ist ein Architect-Kurzplan in job["architect_plan"] gespeichert
  2. StopOptionsFinder-Prompts enthalten Regionsempfehlungen und vorgeschlagene Nächte pro Region
  3. Nächte-Empfehlung basiert auf Ort-Potenzial (z.B. Paris 3 Nächte, Transitort 1 Nacht), nicht immer Minimum
  4. Bei Timeout oder Fehler des Pre-Plans läuft StopOptionsFinder ohne Architect-Kontext weiter (graceful degradation)
**Plans**: TBD

### Phase 14: Stop History Awareness + Night Distribution
**Goal**: StopOptionsFinder schlägt keine bereits ausgewählten Orte vor; Nächteverteilung folgt dem Architect-Plan
**Depends on**: Phase 13
**Requirements**: RTE-03, RTE-04
**Success Criteria** (what must be TRUE):
  1. Bereits ausgewählte Stops erscheinen nicht erneut als Optionen im StopOptionsFinder
  2. Post-Processing Dedup entfernt doppelte Städte als Safety Net, auch wenn der Prompt-Constraint greift
  3. Streaming bleibt nach dem enriched-History-Prompt stabil (erste Option erscheint weiterhin innerhalb 5s)
**Plans**: TBD

### Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation
**Goal**: Geheimtipps liegen wirklich in der Nähe des Stops; Tagespläne bleiben nach Nächteänderungen korrekt
**Depends on**: Phase 12
**Requirements**: ACC-01, ACC-02, BDG-01, BDG-02, BDG-03
**Success Criteria** (what must be TRUE):
  1. Geheimtipp-Hotels mit Entfernung > Schwellwert werden serverseitig ausgefiltert und nicht angezeigt
  2. Doppelte Geheimtipps innerhalb desselben Stops werden entfernt
  3. Nach einer Nächteänderung an einem Stop werden arrival_day für alle nachfolgenden Stops korrekt aktualisiert
  4. User kann Nächte pro Stop über einen dedizierten Button anpassen (nicht nur via prompt() Dialog)
  5. Nach einer Nächte- oder Stop-Änderung startet eine Tagesplan-Neuberechnung via Celery und zeigt SSE-Fortschritt
**Plans**: TBD
**UI hint**: yes

### Phase 16: Frontend UI Fixes + Polish
**Goal**: Die Karte zeigt sofort die Route, Stop-Bilder sind korrekt, Edit-Buttons sind selbsterklärend, die Stop-Auswahlkarte gibt vollständigen Kontext
**Depends on**: Phase 15
**Requirements**: UIX-01, UIX-02, UIX-03, UIX-04
**Success Criteria** (what must be TRUE):
  1. Beim Öffnen einer gespeicherten Reise zoomt die Karte automatisch auf die gesamte Route (fitBounds)
  2. Bilder in der Stop-Übersicht zeigen den richtigen Ort (kein falscher Bildpfad)
  3. Alle Stop-Edit-Buttons haben einen sichtbaren Tooltip beim Hover
  4. In der Stop-Auswahl sind alle bereits ausgewählten Stops auf der Karte sichtbar und die Karte zoomt auf den letzten ausgewählten Stop plus die neuen Optionen
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. AI Quality Stabilization | v1.0 | 3/3 | Complete | 2026-03-25 |
| 2. Geographic Routing | v1.0 | 2/2 | Complete | 2026-03-25 |
| 3. Route Editing | v1.0 | 3/3 | Complete | 2026-03-25 |
| 4. Map-Centric Responsive Layout | v1.0 | 6/6 | Complete | 2026-03-26 |
| 5. Sharing & Cleanup | v1.0 | 3/3 | Complete | 2026-03-26 |
| 6. Wiring Fixes | v1.0 | 2/2 | Complete | 2026-03-26 |
| 7. Ferry-Aware Route Edits | v1.0 | 1/1 | Complete | 2026-03-26 |
| 8. Tech Debt Stabilization | v1.1 | 2/2 | Complete | 2026-03-27 |
| 9. Guide Module Split | v1.1 | 2/2 | Complete | 2026-03-27 |
| 10. Progressive Disclosure UI | v1.1 | 3/3 | Complete | 2026-03-27 |
| 11. Browser Verification | v1.1 | 4/4 | Complete | 2026-03-28 |
| 12. Context Infrastructure + Wishes Forwarding | v1.2 | 1/2 | In Progress|  |
| 13. Architect Pre-Plan for Interactive Flow | v1.2 | 0/? | Not started | - |
| 14. Stop History Awareness + Night Distribution | v1.2 | 0/? | Not started | - |
| 15. Hotel Geheimtipp Quality + Day Plan Recalculation | v1.2 | 0/? | Not started | - |
| 16. Frontend UI Fixes + Polish | v1.2 | 0/? | Not started | - |
