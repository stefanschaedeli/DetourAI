---
phase: 5
slug: sharing-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ |
| **Config file** | None (conventions in CLAUDE.md) |
| **Quick run command** | `cd backend && python3 -m pytest tests/ -v --tb=short` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/ -v --tb=short`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | SHR-01 | unit | `pytest tests/test_travel_db.py::test_share_token_set -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | SHR-01 | integration | `pytest tests/test_endpoints.py::test_share_endpoint -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | SHR-02 | integration | `pytest tests/test_endpoints.py::test_shared_public_access -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | SHR-02 | integration | `pytest tests/test_endpoints.py::test_shared_invalid_token -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | SHR-03 | integration | `pytest tests/test_endpoints.py::test_unshare_endpoint -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | SHR-03 | integration | `pytest tests/test_endpoints.py::test_revoked_token_404 -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | SHR-04 | unit | `pytest tests/test_cleanup.py::test_no_output_generator -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | SHR-04 | integration | `pytest tests/test_endpoints.py::test_generate_output_removed -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_travel_db.py` — add share token CRUD tests (set, get_by_token, clear)
- [ ] `tests/test_endpoints.py` — add share/unshare/public-access endpoint tests
- [ ] Remove `test_output_generator_instantiation` from test_agents_mock.py after cleanup

*Existing infrastructure covers test framework — only new test cases needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Shared view renders full guide with map | SHR-02 | Frontend visual rendering | Open shared link in incognito browser, verify map + cards + timeline visible |
| Share toggle UX in guide header | SHR-01 | Interactive UI behavior | Click Teilen button, verify toggle + copy link + Kopiert! feedback |
| Revoke confirmation dialog | SHR-03 | Interactive UI behavior | Toggle share off, verify confirmation prompt appears |
| Export buttons removed from guide | SHR-04 | Frontend visual check | Open guide view, verify no PDF/PPTX buttons |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
