# Phase 5: Sharing & Cleanup - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can share saved trip plans via public links (read-only, no auth required) and the deprecated PDF/PPTX export is fully removed from the codebase.

</domain>

<decisions>
## Implementation Decisions

### Link Format & Storage
- **D-01:** URL pattern: `/travel/{id}?share={token}` — reuses existing `/travel/{id}` route, share token as query parameter
- **D-02:** Share token stored as `share_token` column on the `travels` table (NULL = not shared, value = active link)
- **D-03:** One share link per trip — generating a new link replaces any existing token
- **D-04:** No expiry — link stays active until user explicitly revokes it

### Shared View Experience
- **D-05:** Full guide view (map-centric layout with cards, timeline, stats) in read-only mode — reuses all Phase 4 UI components but hides edit controls, route editing, and owner-only actions
- **D-06:** Interactive Google Map with markers and polyline (same as owner view, uses API key)
- **D-07:** Subtle footer note: "Erstellt mit DetourAI" at the bottom of shared views

### Share Management UX
- **D-08:** Share button ("Teilen") in the guide view header, next to the trip title
- **D-09:** Inline toggle + copy pattern — toggle switch enables/disables sharing; when on, shows link with copy button. No modal.
- **D-10:** Revoke requires confirmation prompt: "Link deaktivieren? Bestehende Empfaenger verlieren Zugriff."
- **D-11:** Copy feedback: button text changes "Kopieren" -> "Kopiert!" for 2 seconds, then reverts

### PDF/PPTX Removal
- **D-12:** Full removal — delete output_generator.py, /generate-output endpoint, export buttons in guide.js, fpdf2/python-pptx from requirements.txt, outputs/ directory
- **D-13:** Full cleanup — remove Docker volume mounts for outputs/, test references to output generation, update CLAUDE.md and docs to remove all mentions

### Claude's Discretion
- Share token format and length (e.g., UUID, nanoid, secrets.token_urlsafe)
- Backend endpoint structure for share/unshare API calls
- How the shared view detects "read-only mode" (query param check vs. separate route handler)
- Migration strategy for adding share_token column to existing travels table

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend
- `backend/utils/travel_db.py` — Travel persistence layer, schema definition, migration pattern
- `backend/main.py` — All API endpoints including /generate-output (to be removed), auth dependency pattern
- `backend/utils/auth.py` — JWT auth, get_current_user/get_current_user_sse dependencies
- `backend/agents/output_generator.py` — PDF/PPTX agent (to be fully removed)
- `backend/requirements.txt` — Dependencies including fpdf2/python-pptx (to be removed)

### Frontend
- `frontend/js/guide.js` — Travel guide view, export buttons (to be removed), guide header area
- `frontend/js/router.js` — Client-side routing, /travel/{id} route handler
- `frontend/js/api.js` — Fetch wrappers, _fetchWithAuth pattern
- `frontend/js/travels.js` — Saved travels list management

### Infrastructure
- `docker-compose.yml` — Volume mounts for outputs/ (to be removed)
- `CLAUDE.md` — Project documentation referencing output generation (to be updated)
- `DESIGN_GUIDELINE.md` — Apple-inspired design system for share UI styling

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `travel_db.py` migration pattern: `ALTER TABLE ... ADD COLUMN` with try/except for idempotent migrations — use same pattern for share_token column
- `get_current_user` FastAPI dependency — shared endpoint needs to bypass this for unauthenticated viewers
- `_fetchWithAuth()` in api.js — shared view needs a fetch path that works without auth token
- Full Phase 4 guide UI (map, cards, timeline, stats bar) — reuse as-is for shared view in read-only mode

### Established Patterns
- Router pattern in router.js — add query param detection for `?share=` token
- `esc()` function for XSS prevention — use for share token display
- All user-facing text in German — share UI labels follow this convention

### Integration Points
- Guide view header — where share toggle button goes
- `/travel/{id}` route — needs to handle both authenticated owner view and shared token view
- `travels` table — add share_token column via migration

</code_context>

<specifics>
## Specific Ideas

- Share toggle should feel lightweight and inline — no modal dialogs
- Shared view is the same rich guide view, not a dumbed-down version
- "Erstellt mit DetourAI" footer is subtle branding, not a call-to-action

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-sharing-cleanup*
*Context gathered: 2026-03-26*
