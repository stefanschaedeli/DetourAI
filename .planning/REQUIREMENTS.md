# Requirements: DetourAI

**Defined:** 2026-03-29
**Core Value:** Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type — mainland, coastal, and island regions alike.

## v1.2 Requirements

Requirements for milestone v1.2: AI-Qualität & Routenplanung. Each maps to roadmap phases.

### Context Forwarding

- [x] **CTX-01**: User kann globale Aktivitätswünsche als Freitext im Trip-Formular eingeben
- [x] **CTX-02**: `travel_description` und `preferred_activities` werden an alle 9 Agents weitergeleitet
- [x] **CTX-03**: `mandatory_activities` werden an StopOptionsFinder und ActivitiesAgent weitergeleitet

### Route Intelligence

- [x] **RTE-01**: Vor der Stopauswahl erstellt ein Architect Pre-Plan die Regionen und Nächte-Verteilung
- [x] **RTE-02**: StopOptionsFinder erhält Architect-Kontext (Regionen, empfohlene Nächte, Route-Logik)
- [ ] **RTE-03**: StopOptionsFinder kennt alle bisherigen Stops und schlägt keine Duplikate vor
- [ ] **RTE-04**: Post-Processing Dedup verhindert doppelte Städte als Safety Net
- [x] **RTE-05**: Nächte-Verteilung basiert auf Ort-Potenzial statt immer Minimum

### Budget & Tagesplanung

- [x] **BDG-01**: `arrival_day` wird bei jeder Nächte-Änderung korrekt neu berechnet
- [x] **BDG-02**: User kann Nächte pro Stop anpassen (dedizierter Edit-Button)
- [x] **BDG-03**: Tagesplan wird nach Nächte- oder Stop-Änderungen neu berechnet (Celery Task)

### Unterkunftsqualität

- [ ] **ACC-01**: Hotel-Geheimtipps werden serverseitig per Haversine auf Entfernung validiert
- [ ] **ACC-02**: Geheimtipp-Duplikate innerhalb eines Stops werden entfernt

### UI/UX

- [ ] **UIX-01**: Karte beim Öffnen einer Reise auf Route fokussiert (fitBounds)
- [ ] **UIX-02**: Korrekte Bilder in der Stopp-Übersicht
- [ ] **UIX-03**: Tooltips für alle Stop-Edit-Buttons
- [ ] **UIX-04**: Bei Stopauswahl: alle bisherigen Stops sichtbar, Zoom auf letzte + neue Optionen

## Future Requirements

Deferred to v2+. Tracked but not in current roadmap.

### Conversational Planning

- **CONV-01**: Echtzeit-Verhandlung über Nächte-Verteilung im Chat-Format
- **CONV-02**: Globale besuchte-Orte-Datenbank über Trips hinweg

### Parallel Processing

- **PARA-01**: Parallele Tagesplan-Regenerierung für alle Stops nach jeder Änderung

## Out of Scope

| Feature | Reason |
|---------|--------|
| Fuzzy Hotel-Deduplizierung über Stops hinweg | False Positives überwiegen Nutzen; within-stop exact dedup reicht |
| Chatbot-UX für Nächte-Verhandlung | Konflikte mit bestehendem Formular-Flow; erhöht Latenz |
| Scipy/numpy für Nächte-Verteilung | stdlib math reicht; 50MB+ Docker-Image-Overhead |
| LangChain/Agent-Frameworks | Saubere Custom-Agent-Pattern bereits in Produktion |
| Tooltip-JS-Library (tippy.js) | CSS `[data-tooltip]::after` reicht; null Frontend-Dependencies |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CTX-01 | Phase 12 | Complete |
| CTX-02 | Phase 12 | Complete |
| CTX-03 | Phase 12 | Complete |
| RTE-01 | Phase 13 | Complete |
| RTE-02 | Phase 13 | Complete |
| RTE-05 | Phase 13 | Complete |
| RTE-03 | Phase 14 | Pending |
| RTE-04 | Phase 14 | Pending |
| ACC-01 | Phase 15 | Pending |
| ACC-02 | Phase 15 | Pending |
| BDG-01 | Phase 15 | Complete |
| BDG-02 | Phase 15 | Complete |
| BDG-03 | Phase 15 | Complete |
| UIX-01 | Phase 16 | Pending |
| UIX-02 | Phase 16 | Pending |
| UIX-03 | Phase 16 | Pending |
| UIX-04 | Phase 16 | Pending |

**Coverage:**
- v1.2 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap creation*
