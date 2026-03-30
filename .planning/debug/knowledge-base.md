# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## loading-js-travels-js-reference-errors — i18n.js loaded after loading.js causing t() ReferenceError at module init
- **Date:** 2026-03-30
- **Error patterns:** ReferenceError, t is not defined, showLoading is not defined, loading.js, travels.js, i18n, script load order
- **Root cause:** index.html loaded loading.js before i18n.js. loading.js calls t() as a variable initializer inside its IIFE (module level, not inside a function). Since window.t did not exist yet when the script ran, the IIFE threw a ReferenceError and exited before assigning window.showLoading, causing a second ReferenceError when travels.js later called showLoading().
- **Fix:** Swapped script load order in index.html so i18n.js loads before loading.js, ensuring window.t is defined before loading.js runs.
- **Files changed:** frontend/index.html
---
