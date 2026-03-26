# Phase 2: Geographic Routing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 02-geographic-routing
**Areas discussed:** Ferry Detection Strategy, Port/Island Knowledge Base, Google Directions Failure Handling, Daily Schedule Impact
**Mode:** Auto (--auto flag)

---

## Ferry Detection Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Haversine over water detection | Detect ferry need via haversine vs driving distance divergence + AI identification | ✓ |
| Static route database | Maintain a database of known ferry routes | |
| Google Transit API | Use transit mode in Google Directions for ferry routes | |

**User's choice:** [auto] Haversine over water detection (recommended default)
**Notes:** Combines AI reasoning (route architect identifies ferry segments) with algorithmic validation (haversine vs driving distance check). Most flexible approach.

### Sub-question: Ferry visualization

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated ferry leg | Ferry appears as distinct segment in route | ✓ |
| Merged into driving leg | Ferry time added to adjacent driving leg | |

**User's choice:** [auto] Dedicated ferry leg (recommended default)
**Notes:** Better user clarity — ferry crossings are significant events that deserve their own representation.

---

## Port/Island Knowledge Base

| Option | Description | Selected |
|--------|-------------|----------|
| AI-generated with validation | Claude identifies ports, lightweight lookup table validates | ✓ |
| Comprehensive static database | Full ferry port database maintained manually | |
| Pure AI | Let Claude handle all port identification without validation | |

**User's choice:** [auto] AI-generated with validation (recommended default)
**Notes:** Balances accuracy with maintainability. Claude-opus handles the reasoning; lookup table catches obvious errors.

### Sub-question: Coverage scope

| Option | Description | Selected |
|--------|-------------|----------|
| Common Mediterranean | Greek islands, Corsica, Sardinia, Sicily, Balearics, Croatian islands | ✓ |
| Europe-wide | Include Scandinavian, UK, Baltic ferries | |
| Global | All ferry routes worldwide | |

**User's choice:** [auto] Common Mediterranean (recommended default)
**Notes:** Matches the app's primary use case (European road trips). AI handles edge cases beyond the lookup table.

---

## Google Directions Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Haversine estimate with ferry flag | Calculate haversine distance, estimate ferry time at ~30 km/h, flag as is_ferry | ✓ |
| Fail with suggestion | Return error suggesting user adjust route | |
| Try transit mode | Attempt Google Transit API before falling back | |

**User's choice:** [auto] Haversine estimate with ferry flag (recommended default)
**Notes:** Never fail a route because of water. Construct a plausible estimate and let the user see it.

### Sub-question: Retry strategy

| Option | Description | Selected |
|--------|-------------|----------|
| No retry, construct estimate | Don't waste API calls — Google won't find driving routes across water | ✓ |
| Retry with ferry port waypoints | Add known ferry ports as waypoints and retry | |

**User's choice:** [auto] No retry, construct estimate (recommended default)
**Notes:** Google Directions driving mode will never route across water. Retrying wastes API quota.

---

## Daily Schedule Impact

| Option | Description | Selected |
|--------|-------------|----------|
| Deduct from daily max | Ferry time reduces available driving hours for the day | ✓ |
| Separate ferry budget | Ferry time doesn't count against driving budget | |
| Travel day | Ferry crossings consume entire travel days | |

**User's choice:** [auto] Deduct from daily max (recommended default)
**Notes:** Most realistic — a 3-hour ferry on a 4.5h budget leaves 1.5h driving. Keeps schedules honest.

### Sub-question: Ferry cost tracking

| Option | Description | Selected |
|--------|-------------|----------|
| Separate ferry cost line | ferries_chf as distinct budget category (field already exists) | ✓ |
| Merged into fuel/transport | Ferry cost absorbed into transport category | |

**User's choice:** [auto] Separate ferry cost line (recommended default)
**Notes:** Field already exists in output generator. Keep ferry costs visible and distinct.

---

## Claude's Discretion

- Exact haversine/driving distance divergence threshold
- Ferry speed estimate tuning
- Lookup table format and structure
- Number of port alternatives per island group
- German-language SSE message wording
- Ferry duration display format (range vs point estimate)

## Deferred Ideas

None — discussion stayed within phase scope
