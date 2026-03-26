# Phase 6: Wiring Fixes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 06-wiring-fixes
**Areas discussed:** Share toggle reload, Replace-stop hints UI, SSE warning display, Stop tags generation

---

## Share toggle reload

| Option | Description | Selected |
|--------|-------------|----------|
| API refetch is fine | Current flow calls apiGetTravel() on reload which returns share_token. Just ensure toggle reads it correctly. Simplest fix. | ✓ |
| localStorage cache | Cache share_token in tp_v1_* keys. Faster initial render but staleness risk. | |
| You decide | Claude picks approach | |

**User's choice:** API refetch is fine
**Notes:** None — straightforward decision.

---

## Replace-stop hints UI

| Option | Description | Selected |
|--------|-------------|----------|
| Text input field | Simple text input in replace-stop dialog with placeholder 'z.B. mehr Strand, weniger Fahrzeit'. Backend already accepts freeform string. | ✓ |
| Preset chips + text input | Quick-select chips plus freeform text input. Richer UX but more work. | |
| Preset chips only | Fixed set of hint buttons, no freeform. Limits user expression. | |
| You decide | Claude picks approach | |

**User's choice:** Text input field
**Notes:** None.

**Follow-up: Required or optional?**

| Option | Description | Selected |
|--------|-------------|----------|
| Optional | User can leave empty — replace works as before. No friction added. | ✓ |
| Required | Force user to explain what they want differently. | |

**User's choice:** Optional
**Notes:** None.

---

## SSE warning display

| Option | Description | Selected |
|--------|-------------|----------|
| Toast notification | Brief auto-dismissing toast. Non-blocking. | ✓ |
| Inline banner on stop | Warning banner on affected stop card. More contextual. | |
| Badge on stop card | Small warning icon/badge. Subtle, persistent. | |
| You decide | Claude picks | |

**User's choice:** Toast notification
**Notes:** None.

**Follow-up: ferry_detected style?**

| Option | Description | Selected |
|--------|-------------|----------|
| Informational (blue/neutral) | Just FYI, no action needed. Ferries aren't problems. | ✓ |
| Warning style (amber) | Draws more attention. | |

**User's choice:** Informational
**Notes:** User added: "ensure that cost of ferries are added to the budget" — captured as D-08 in CONTEXT.md.

---

## Stop tags generation

| Option | Description | Selected |
|--------|-------------|----------|
| StopOptionsFinder generates them | Tags when stops first suggested. 2-4 tags per stop. | |
| ActivitiesAgent enriches them | Tags added during research. More accurate but delayed. | |
| Both agents contribute | Initial tags from StopOptionsFinder, enriched by ActivitiesAgent. Most complete. | ✓ |
| You decide | Claude picks simplest approach | |

**User's choice:** Both agents contribute
**Notes:** None.

**Follow-up: Language?**

| Option | Description | Selected |
|--------|-------------|----------|
| German | Matches UI convention. 'Strand', 'Kultur', 'Wandern'. | ✓ |
| English | 'Beach', 'Culture', 'Hiking'. More modern but breaks convention. | |

**User's choice:** German
**Notes:** User noted: "keep on german at the moment. in a bigger change in the future i will ask to rebuild the app with full multi language implementation if required"

**Follow-up: Max tags per stop?**

| Option | Description | Selected |
|--------|-------------|----------|
| 3-4 tags | Descriptive without cluttering. Fits pill layout. | ✓ |
| 2 tags max | Very minimal. Clean but less informative. | |
| Up to 6 tags | Comprehensive. Risk of visual clutter. | |

**User's choice:** 3-4 tags
**Notes:** None.

---

## Claude's Discretion

- Toast notification styling and positioning
- Exact tag vocabulary
- Tag deduplication strategy when both agents contribute

## Deferred Ideas

- Multi-language support — user plans future rebuild
- Preset hint chips for replace-stop — text input sufficient for now
