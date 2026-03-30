---
status: resolved
trigger: "Console errors when opening a previously saved travel. Two ReferenceErrors break the page."
created: 2026-03-30T00:00:00Z
updated: 2026-03-30T00:00:00Z
---

## Current Focus

hypothesis: loading.js executes before i18n.js is loaded, so t() is undefined at module evaluation time; travels.js calls showLoading() which is defined inside a loading.js IIFE but the IIFE throws at line 5 before ever reaching the window.showLoading = ... assignment, so showLoading never gets set on window.
test: Verified by reading load order in index.html (loading.js line 779, i18n.js line 780) and reading loading.js line 5 which calls t() at module-level initialization inside the IIFE.
expecting: Both bugs stem from a single root cause: loading order
next_action: Fix index.html to load i18n.js before loading.js

## Symptoms

expected: Opening a saved travel should load without JS errors
actual: Two ReferenceErrors appear in the browser console, preventing the page from working correctly
errors:
  1. loading.js:5 Uncaught ReferenceError: t is not defined at loading.js:5:23
  2. travels.js:132 Uncaught (in promise) ReferenceError: showLoading is not defined
reproduction: Open the travels list page and click to open a previously saved travel
started: After i18n work — "feat: i18n — add ~200 new translation keys + getFormattingLocale helper"

## Eliminated

- hypothesis: showLoading is not defined because it was removed from loading.js
  evidence: window.showLoading is defined at loading.js:53, but the IIFE throws before reaching that line
  timestamp: 2026-03-30T00:00:00Z

## Evidence

- timestamp: 2026-03-30T00:00:00Z
  checked: index.html script load order (lines 779-780)
  found: loading.js is loaded at line 779, i18n.js at line 780 — i18n.js comes AFTER loading.js
  implication: When loading.js IIFE runs, window.t is not yet defined → ReferenceError at line 5

- timestamp: 2026-03-30T00:00:00Z
  checked: loading.js lines 3-6
  found: IIFE starts, line 5 calls t('loading.default') at module initialization time (not inside a function, but as a variable initializer)
  implication: t() is called synchronously when the script loads, before i18n.js has run → throws ReferenceError → entire IIFE aborts → window.showLoading never assigned

- timestamp: 2026-03-30T00:00:00Z
  checked: travels.js line 132
  found: openSavedTravel() calls showLoading(...) which must be window.showLoading from loading.js
  implication: Because loading.js IIFE threw before assigning window.showLoading, the function doesn't exist → second ReferenceError

- timestamp: 2026-03-30T00:00:00Z
  checked: i18n.js
  found: window.t is set at line 113, but only after the IIFE runs. i18n.js loads synchronously and exposes t() globally. It must be loaded before any script that calls t() at module level.
  implication: Fix is to swap load order: i18n.js before loading.js in index.html

## Resolution

root_cause: index.html loads loading.js (line 779) before i18n.js (line 780). loading.js calls t('loading.default') at module initialization time (line 5, as a variable initializer). Since t() is not yet defined when loading.js runs, the IIFE throws a ReferenceError and exits immediately, meaning window.showLoading is never assigned. When travels.js later calls showLoading(), it gets a second ReferenceError because the first failure prevented the assignment.
fix: Swapped script load order in index.html so i18n.js (line 779) now loads before loading.js (line 780). i18n.js exposes window.t globally before loading.js runs, so the t() call at loading.js:5 no longer throws. The IIFE now completes and assigns window.showLoading correctly.
verification: Confirmed by user — app works again, no more console errors
files_changed: [frontend/index.html]
