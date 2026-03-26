# Phase 5: Sharing & Cleanup - Research

**Researched:** 2026-03-26
**Domain:** Share link generation, public read-only views, legacy code removal
**Confidence:** HIGH

## Summary

Phase 5 has two distinct tracks: (1) shareable public links for saved trips and (2) removal of the deprecated PDF/PPTX export. Both are well-scoped with clear boundaries.

The sharing feature requires a new `share_token` column on the `travels` table, a public API endpoint that bypasses JWT auth, frontend detection of `?share=` query parameter to render read-only mode, and a share management UI inline in the guide header. The cleanup track is straightforward deletion of `output_generator.py`, the `/generate-output` endpoint, export buttons, `fpdf2`/`python-pptx` dependencies, and `outputs/` references.

**Primary recommendation:** Use `secrets.token_urlsafe(16)` for share tokens (22 chars, URL-safe, cryptographically random). Add a single public endpoint `GET /api/shared/{token}` that returns plan_json without auth. Frontend detects shared mode via query param and conditionally hides edit controls.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** URL pattern: `/travel/{id}?share={token}` -- reuses existing `/travel/{id}` route, share token as query parameter
- **D-02:** Share token stored as `share_token` column on the `travels` table (NULL = not shared, value = active link)
- **D-03:** One share link per trip -- generating a new link replaces any existing token
- **D-04:** No expiry -- link stays active until user explicitly revokes it
- **D-05:** Full guide view (map-centric layout with cards, timeline, stats) in read-only mode -- reuses all Phase 4 UI components but hides edit controls, route editing, and owner-only actions
- **D-06:** Interactive Google Map with markers and polyline (same as owner view, uses API key)
- **D-07:** Subtle footer note: "Erstellt mit Travelman" at the bottom of shared views
- **D-08:** Share button ("Teilen") in the guide view header, next to the trip title
- **D-09:** Inline toggle + copy pattern -- toggle switch enables/disables sharing; when on, shows link with copy button. No modal.
- **D-10:** Revoke requires confirmation prompt: "Link deaktivieren? Bestehende Empfaenger verlieren Zugriff."
- **D-11:** Copy feedback: button text changes "Kopieren" -> "Kopiert!" for 2 seconds, then reverts
- **D-12:** Full removal -- delete output_generator.py, /generate-output endpoint, export buttons in guide.js, fpdf2/python-pptx from requirements.txt, outputs/ directory
- **D-13:** Full cleanup -- remove Docker volume mounts for outputs/, test references to output generation, update CLAUDE.md and docs to remove all mentions

### Claude's Discretion
- Share token format and length (e.g., UUID, nanoid, secrets.token_urlsafe)
- Backend endpoint structure for share/unshare API calls
- How the shared view detects "read-only mode" (query param check vs. separate route handler)
- Migration strategy for adding share_token column to existing travels table

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SHR-01 | User can generate a public shareable link for any saved trip plan | Share token generation via `secrets.token_urlsafe(16)`, stored as `share_token` column, toggle UI in guide header |
| SHR-02 | Shared link shows a read-only view of the full trip plan (no authentication required) | Public endpoint `GET /api/shared/{token}` bypasses auth; frontend `S.sharedMode` flag hides edit controls |
| SHR-03 | User can revoke (disable) a previously shared link | Set `share_token = NULL` via PATCH endpoint; confirmation prompt before revocation |
| SHR-04 | PDF/PPTX export functionality is removed from the codebase | Delete output_generator.py, endpoint, buttons, deps, volume mounts, test references, docs |
</phase_requirements>

## Architecture Patterns

### Backend: Share Token Flow

**Token generation (recommendation: `secrets.token_urlsafe(16)`):**
- Produces 22-character URL-safe string (base64url-encoded 16 random bytes)
- Cryptographically random via `os.urandom()` -- no collision risk
- URL-safe: only uses `[A-Za-z0-9_-]` -- safe in query params without encoding
- Python stdlib -- no additional dependency

**Confidence:** HIGH -- `secrets` module is the Python standard for security tokens since Python 3.6.

### Recommended Endpoint Structure

```
POST   /api/travels/{travel_id}/share    -- generate or regenerate share token
DELETE /api/travels/{travel_id}/share    -- revoke (set NULL)
GET    /api/shared/{token}               -- public: fetch plan by share_token (NO auth)
```

**Key design choice:** The public endpoint is `GET /api/shared/{token}` (separate from `/api/travels/{id}`) to cleanly separate authenticated and public access paths. This avoids complex optional-auth logic on the existing endpoint.

### Database Migration

Add migration version 6 to `backend/utils/migrations.py`:

```python
(
    6,
    "travels_add_share_token",
    lambda conn: _add_column_if_missing(conn, "travels", "share_token", "TEXT"),
),
```

This follows the exact established pattern (versions 3-5 use `_add_column_if_missing`). The column is nullable by default (NULL = not shared). No index needed -- lookups by share_token will be rare and the travels table is small.

**Confidence:** HIGH -- verified the migration pattern in `migrations.py` (5 existing migrations, all use the same structure).

### travel_db.py Changes

New functions needed:

```python
def _sync_set_share_token(travel_id: int, user_id: int, token: Optional[str]) -> bool:
    """Set or clear share_token for a travel owned by user_id."""
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE travels SET share_token = ? WHERE id = ? AND user_id = ?",
            (token, travel_id, user_id),
        )
    return cur.rowcount > 0

def _sync_get_by_share_token(token: str) -> Optional[dict]:
    """Fetch plan_json by share_token (public, no user_id check)."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, plan_json FROM travels WHERE share_token = ?",
            (token,),
        ).fetchone()
    if row is None:
        return None
    plan = json.loads(row["plan_json"])
    plan["_saved_travel_id"] = row["id"]
    return plan
```

Plus async wrappers following the existing pattern.

**Confidence:** HIGH -- directly mirrors existing `_sync_get` and `_sync_update` patterns.

### Frontend: Shared Mode Detection

**Recommended approach:** Detect `?share=` query parameter in the router's `_travel` handler.

```javascript
// In router.js _travel handler:
async _travel(m) {
  const id = parseInt(m[1], 10);
  const shareToken = new URLSearchParams(location.search).get('share');

  if (shareToken) {
    // Public shared view -- fetch without auth
    const plan = await apiGetShared(shareToken);
    plan._saved_travel_id = id;
    plan._shared = true;  // flag for read-only mode
    S.result = plan;
    S.sharedMode = true;
    showTravelGuide(plan);
    showSection('travel-guide');
    return;
  }
  // ... existing authenticated flow
}
```

**Read-only mode enforcement:** Set `S.sharedMode = true` and check this flag in:
- `guide.js` -- hide replan button, share toggle (show only for owner), edit controls
- `guide.js` -- hide drag-and-drop reorder handlers
- `guide.js` -- hide remove/replace/add stop buttons
- `guide.js` -- show "Erstellt mit Travelman" footer
- `sidebar.js` -- hide sidebar navigation (shared view is standalone)

**API fetch for shared view:**
```javascript
async function apiGetShared(token) {
  // Use plain fetch -- no auth needed for shared endpoint
  const res = await fetch(`${API}/shared/${token}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

This must NOT use `_fetchWithAuth()` since the viewer has no JWT token.

**Confidence:** HIGH -- straightforward query param detection and conditional rendering.

### Share Management UI

Location: `.guide-header-row` in `index.html` (line 545), next to "Ihr Reiseplan" h2 and replan button.

```html
<div class="guide-header-row">
  <h2>Ihr Reiseplan</h2>
  <div class="guide-header-actions">
    <div class="share-toggle-container" id="share-toggle-container" style="display:none">
      <!-- JS-rendered: toggle switch + copy URL -->
    </div>
    <button class="btn btn-secondary btn-sm replan-btn" id="replan-current-btn" ...>
  </div>
</div>
```

The share toggle container is hidden by default and shown only when viewing an owned (non-shared) travel. The toggle switch, URL display, and copy button are rendered by JS.

### PDF/PPTX Removal Inventory

Files/sections to delete or modify:

| File | Action | What |
|------|--------|------|
| `backend/agents/output_generator.py` | DELETE entirely | ~200 lines, PDF/PPTX generation |
| `backend/main.py` lines 191-192 | REMOVE | `OUTPUTS_DIR` constant and `mkdir` |
| `backend/main.py` lines 2038-2069 | REMOVE | `/api/generate-output/{job_id}/{file_type}` endpoint |
| `backend/requirements.txt` lines 12-13 | REMOVE | `fpdf2>=2.7.9`, `python-pptx>=0.6.23` |
| `frontend/js/guide.js` lines 2073-2077 | REMOVE | Export buttons HTML in `renderBudget()` |
| `frontend/js/guide.js` lines 2082-2101 | REMOVE | `generateOutput()` function |
| `frontend/js/api.js` lines 171-175 | REMOVE | `apiGenerateOutput()` function |
| `backend/tests/test_agents_mock.py` lines 319-323 | REMOVE | `test_output_generator_instantiation` test |
| `docker-compose.yml` line 26 | REMOVE | `OUTPUTS_DIR=/app/outputs` env var |
| `docker-compose.yml` line 44 | REMOVE | `./outputs:/app/outputs` volume mount |
| `CLAUDE.md` | UPDATE | Remove all output_generator.py, PDF/PPTX, outputs/ references |

**Confidence:** HIGH -- grep audit located all references.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Share token generation | Custom random string | `secrets.token_urlsafe(16)` | Cryptographically secure, URL-safe, stdlib |
| Clipboard copy | Manual execCommand | `navigator.clipboard.writeText()` | Modern API, supported in all current browsers |
| Toggle switch CSS | Custom checkbox hack | Standard CSS toggle pattern with `<input type="checkbox">` | Accessibility built-in, keyboard-friendly |

## Common Pitfalls

### Pitfall 1: Shared View Leaking Edit Actions
**What goes wrong:** Shared viewers see edit buttons (replan, remove stop, drag reorder) that trigger 401 errors when clicked.
**Why it happens:** Read-only flag not checked in every rendering branch.
**How to avoid:** Set `S.sharedMode = true` early (before any rendering). Check it in every function that renders action buttons. Test by opening a shared link in an incognito window.
**Warning signs:** 401 errors in browser console on shared view.

### Pitfall 2: Auth Wrapper on Public Endpoint
**What goes wrong:** `apiGetShared()` uses `_fetchWithAuth()` which triggers login redirect when no token exists.
**Why it happens:** Developer habit of using the auth wrapper for all API calls.
**How to avoid:** Use plain `fetch()` for the shared endpoint. Put `apiGetShared()` in api.js clearly marked as public.

### Pitfall 3: Share Token in URL Not Preserved on Tab Navigation
**What goes wrong:** User opens shared link, clicks a tab (stops, days), loses the `?share=` param.
**Why it happens:** `Router.navigate()` for tab URLs doesn't carry the share query param.
**How to avoid:** When `S.sharedMode` is true, append `?share=${token}` to all internal navigation URLs. Store the token in `S.shareToken`.

### Pitfall 4: Incomplete PDF/PPTX Removal
**What goes wrong:** Orphaned import or reference causes ImportError or dead code.
**Why it happens:** Missing a reference in one of many files.
**How to avoid:** After removal, run `grep -r "output_generator\|generate.output\|fpdf2\|python-pptx\|OUTPUTS_DIR\|generateOutput\|apiGenerateOutput" .` to verify zero hits.

### Pitfall 5: Migration Not Run on Existing Database
**What goes wrong:** `share_token` column missing at runtime, queries fail.
**Why it happens:** Migration system not invoked, or `_init_db()` in `travel_db.py` also needs the column.
**How to avoid:** Add the migration to `migrations.py` (formal migration system). Also add a try/except `ALTER TABLE` in `_init_db()` for the `share_token` column (matches existing pattern for `has_travel_guide`, `custom_name`, `rating`).

## Code Examples

### Share Token Generation (Backend)
```python
# Source: Python stdlib secrets module
import secrets

def generate_share_token() -> str:
    """Generate a 22-char URL-safe share token."""
    return secrets.token_urlsafe(16)
```

### Public Endpoint (Backend)
```python
# No auth dependency -- public access
@app.get("/api/shared/{token}")
async def api_get_shared_travel(token: str):
    plan = await get_travel_by_share_token(token)
    if plan is None:
        raise HTTPException(404, detail="Geteilter Link nicht gefunden oder deaktiviert")
    return plan
```

### Share Toggle UI (Frontend)
```javascript
// Inline toggle + copy pattern (D-09)
function renderShareToggle(travelId, shareToken) {
  const isShared = !!shareToken;
  const shareUrl = isShared
    ? `${location.origin}/travel/${travelId}?share=${shareToken}`
    : '';

  return `
    <div class="share-control">
      <label class="toggle-switch">
        <input type="checkbox" ${isShared ? 'checked' : ''}
               onchange="toggleShare(${travelId}, this.checked)">
        <span class="toggle-slider"></span>
      </label>
      <span class="share-label">Teilen</span>
      ${isShared ? `
        <input type="text" class="share-url-input" value="${esc(shareUrl)}" readonly>
        <button class="btn btn-sm" onclick="copyShareLink(this, '${esc(shareUrl)}')">Kopieren</button>
      ` : ''}
    </div>
  `;
}
```

### Clipboard Copy with Feedback (Frontend)
```javascript
// D-11: Copy feedback
async function copyShareLink(btn, url) {
  await navigator.clipboard.writeText(url);
  const original = btn.textContent;
  btn.textContent = 'Kopiert!';
  setTimeout(() => { btn.textContent = original; }, 2000);
}
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | None (conventions in CLAUDE.md) |
| Quick run command | `cd backend && python3 -m pytest tests/ -v --tb=short` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SHR-01 | Generate share token and store in DB | unit | `pytest tests/test_travel_db.py::test_share_token_set -x` | Wave 0 |
| SHR-01 | POST /api/travels/{id}/share returns token | integration | `pytest tests/test_endpoints.py::test_share_endpoint -x` | Wave 0 |
| SHR-02 | GET /api/shared/{token} returns plan without auth | integration | `pytest tests/test_endpoints.py::test_shared_public_access -x` | Wave 0 |
| SHR-02 | GET /api/shared/{invalid} returns 404 | integration | `pytest tests/test_endpoints.py::test_shared_invalid_token -x` | Wave 0 |
| SHR-03 | DELETE /api/travels/{id}/share clears token | integration | `pytest tests/test_endpoints.py::test_unshare_endpoint -x` | Wave 0 |
| SHR-03 | Revoked token returns 404 on public endpoint | integration | `pytest tests/test_endpoints.py::test_revoked_token_404 -x` | Wave 0 |
| SHR-04 | output_generator.py deleted, import fails | unit | `pytest tests/test_cleanup.py::test_no_output_generator -x` | Wave 0 |
| SHR-04 | /api/generate-output returns 404 | integration | `pytest tests/test_endpoints.py::test_generate_output_removed -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/ -v --tb=short`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_travel_db.py` -- add share token CRUD tests (set, get_by_token, clear)
- [ ] `tests/test_endpoints.py` -- add share/unshare/public-access endpoint tests
- [ ] Remove `test_output_generator_instantiation` from test_agents_mock.py

## Sources

### Primary (HIGH confidence)
- `backend/utils/travel_db.py` -- existing schema, migration pattern, async wrapper pattern
- `backend/utils/migrations.py` -- formal migration system (5 existing versions)
- `backend/utils/auth.py` -- JWT auth dependencies, `get_current_user` pattern
- `backend/main.py` -- all endpoints, OUTPUTS_DIR, generate-output endpoint (lines 2038-2069)
- `frontend/js/router.js` -- routing patterns, `_travel` handler, query param handling
- `frontend/js/guide.js` -- guide rendering, export buttons (lines 2073-2101), `generateOutput()`
- `frontend/js/api.js` -- `_fetchWithAuth()`, `apiGetTravel()`, `apiGenerateOutput()`
- `docker-compose.yml` -- outputs volume mount (line 44)
- `backend/tests/test_agents_mock.py` -- `test_output_generator_instantiation` (line 319)
- Python `secrets` module docs -- `token_urlsafe()` specification

### Secondary (MEDIUM confidence)
- `navigator.clipboard.writeText()` -- modern Clipboard API, supported in all current browsers (Safari 13.1+, Chrome 66+, Firefox 63+)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies needed, all Python stdlib
- Architecture: HIGH -- follows established patterns in the codebase exactly
- Pitfalls: HIGH -- derived from direct code inspection of existing patterns

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (stable domain, no fast-moving dependencies)
