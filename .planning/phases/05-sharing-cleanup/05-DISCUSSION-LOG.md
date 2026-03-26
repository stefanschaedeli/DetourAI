# Phase 5: Sharing & Cleanup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 05-sharing-cleanup
**Areas discussed:** Shared link format, Shared view experience, Share management UX, PDF/PPTX removal scope

---

## Shared Link Format

| Option | Description | Selected |
|--------|-------------|----------|
| Random token path | /shared/a7f3x9k2 — clean, opaque, no travel ID leaked | |
| Travel ID with token query | /travel/42?share=a7f3x9k2 — reuses existing route pattern | ✓ |
| Short readable slug | /s/franz-alpen-paris-2026 — human-readable from trip title | |

**User's choice:** Travel ID with token query
**Notes:** Reuses existing /travel/{id} route pattern

---

| Option | Description | Selected |
|--------|-------------|----------|
| No expiry | Link stays active until manually revoked | ✓ |
| Configurable expiry | User picks 7d / 30d / never | |

**User's choice:** No expiry

---

| Option | Description | Selected |
|--------|-------------|----------|
| One link per trip | Generate replaces existing link, revoke kills the only link | ✓ |
| Multiple links per trip | Each generation creates new token | |

**User's choice:** One link per trip

---

| Option | Description | Selected |
|--------|-------------|----------|
| Column on travels table | Add share_token column, NULL = not shared | ✓ |
| You decide | Let Claude pick | |

**User's choice:** Column on travels table

---

## Shared View Experience

| Option | Description | Selected |
|--------|-------------|----------|
| Full guide view | Same map-centric layout, read-only, reuses Phase 4 UI | ✓ |
| Simplified view | Stripped-down list, no interactive map | |
| Print-friendly view | Linear layout optimized for reading/printing | |

**User's choice:** Full guide view (read-only)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Interactive Google Map | Full map with markers and polyline | ✓ |
| Static map image | Google Static Maps API image | |
| You decide | Let Claude pick | |

**User's choice:** Interactive Google Map

---

| Option | Description | Selected |
|--------|-------------|----------|
| No branding | Clean view, no marketing | |
| Subtle footer note | Small "Erstellt mit Travelman" at bottom | ✓ |
| You decide | Let Claude decide | |

**User's choice:** Subtle footer note

---

## Share Management UX

| Option | Description | Selected |
|--------|-------------|----------|
| In the guide view header | Share button next to trip title | ✓ |
| In the travel list | Share icon on each travel card | |
| Both locations | Guide header AND travel list | |

**User's choice:** In the guide view header

---

| Option | Description | Selected |
|--------|-------------|----------|
| Inline toggle + copy | Toggle switch with copy button, no modal | ✓ |
| Modal dialog | Opens modal with share link and options | |
| You decide | Let Claude pick | |

**User's choice:** Inline toggle + copy

---

| Option | Description | Selected |
|--------|-------------|----------|
| Confirmation prompt | Warning before revoking | ✓ |
| Instant toggle off | No confirmation | |

**User's choice:** Confirmation prompt

---

| Option | Description | Selected |
|--------|-------------|----------|
| Button text changes briefly | "Kopieren" -> "Kopiert!" for 2 seconds | ✓ |
| Toast notification | Small toast at bottom | |
| You decide | Let Claude pick | |

**User's choice:** Button text changes briefly

---

## PDF/PPTX Removal Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Remove everything | Clean sweep — all code, deps, outputs/ dir | ✓ |
| Keep the agent file | Delete endpoints/UI but keep output_generator.py | |
| You decide | Let Claude determine | |

**User's choice:** Remove everything

---

| Option | Description | Selected |
|--------|-------------|----------|
| Full cleanup | Remove volume mounts, test refs, doc mentions | ✓ |
| Code only | Remove code and deps only | |

**User's choice:** Full cleanup

---

## Claude's Discretion

- Share token format and length
- Backend endpoint structure for share/unshare API
- Read-only mode detection approach
- Migration strategy for share_token column

## Deferred Ideas

None — discussion stayed within phase scope
