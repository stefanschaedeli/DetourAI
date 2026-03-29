---
phase: 12
slug: context-infrastructure-wishes-forwarding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | none — pytest discovers automatically |
| **Quick run command** | `cd backend && python3 -m pytest tests/test_agents_mock.py -v -x` |
| **Full suite command** | `cd backend && python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3 -m pytest tests/test_agents_mock.py -v -x`
- **After every plan wave:** Run `cd backend && python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | CTX-01 | manual | browser: Step 2 tag input | N/A (frontend) | ⬜ pending |
| 12-01-02 | 01 | 1 | CTX-01 | manual | browser: buildPayload check | N/A (frontend) | ⬜ pending |
| 12-02-01 | 02 | 1 | CTX-02 | unit | `pytest tests/test_agents_mock.py -v -x` | ✅ existing | ⬜ pending |
| 12-02-02 | 02 | 1 | CTX-02 | unit | `pytest tests/test_agents_mock.py -v -x` | ✅ existing | ⬜ pending |
| 12-02-03 | 02 | 1 | CTX-03 | unit | `pytest tests/test_agents_mock.py -v -x` | ✅ existing | ⬜ pending |
| 12-03-01 | 03 | 2 | CTX-02,CTX-03 | unit | `pytest tests/test_agents_mock.py -v -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_agents_mock.py::test_route_architect_includes_preferred_activities` — verify preferred_activities in RouteArchitect prompt
- [ ] `tests/test_agents_mock.py::test_stop_options_finder_includes_all_wishes` — verify all 3 fields in StopOptionsFinder prompt
- [ ] `tests/test_agents_mock.py::test_wishes_absent_when_empty` — verify no extra lines when fields empty
- [ ] `tests/test_agents_mock.py::test_restaurants_agent_includes_wishes` — verify wishes in RestaurantsAgent prompt

*Existing test infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| preferred_activities tag input renders in Step 2 | CTX-01 | Frontend vanilla JS, no test framework | Open form, go to Step 2, verify tag-chip input appears below travel_description |
| Tags persist in localStorage on page reload | CTX-01 | Browser state | Add tags, reload, verify tags restored |
| buildPayload() includes S.preferredTags | CTX-02 | Frontend payload assembly | Add tags, submit form, check network request body |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
