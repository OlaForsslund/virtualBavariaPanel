# MFD Display Capabilities — B&G Zeus3 7

Captured 2026-07-25 on the boat, via a temporary `window.onerror` +
dimension-reporting beacon added to `webapp/index.html` (see CLAUDE.md,
"MFD app was stuck on 'loading'" for how/why). For offline UI design —
lets you size mockups without the physical MFD in hand.

## Device / browser

- Model: B&G Zeus3 7 (`mfd_model_detail=Zeus3 7` in the app-launch query
  string; `mfd_name` is the boat's own MFD hostname, "Aventyret")
- Browser: `QtWebEngine/5.12.9`, Chromium 69 (`Chrome/69.0.3497.128`)
  — fully supports ES2017 (async/await, arrow fns, template literals,
  destructuring, classes, spread, `fetch`). Does **not** support ES2020+
  (`??`, `?.` throw a `SyntaxError`. See CLAUDE.md for the bug this caused.)
- No service worker support surfaced (`'serviceWorker' in navigator` false)
  — expected, the app is served over plain HTTP and service workers
  require a secure context.
- `devicePixelRatio: 1` — design at 1:1 pixel ratio, no HiDPI scaling.
- Not sandboxed: `window === window.top`, `location.origin` is a real
  origin (not opaque/`null`), same-origin `fetch`/`XHR` work normally.

## Screen / viewport

- Physical screen: **1024 × 600** (`screen.width`/`screen.height`,
  constant regardless of app layout).
- MFD chrome overhead is a constant **26px of height** — every observed
  viewport was exactly 574px tall regardless of split layout, so the
  MFD's own UI (status bar etc.) always eats the same vertical strip.
- Observed viewport **widths** (`window.innerWidth`) across different
  split-screen layouts (heights all 574px):

  | Width | Layout (best guess — not confirmed against MFD screenshots) |
  |-------|----------------------------------------------------------|
  | 803px | Full screen, single pane |
  | 642px | Two-pane split |
  | 398px | Three-pane split (or two-pane + narrower divider position) |
  | 318px | Narrowest observed — three-pane incl. autopilot, or a tighter divider position |

  The 398/318 pair showed up interchangeably while switching between the
  Control and Diagnostics tabs in the same session, so they may reflect
  divider dragging rather than two fixed presets — worth re-verifying
  with a screenshot next time if the exact mapping matters.

## Design takeaway

Design the Control view to remain usable down to **~318px wide** (worst
observed split), at a fixed **574px** tall. No HiDPI concerns. Avoid
ES2020+ syntax (`??`, `?.`) anywhere in shipped code — this MFD's
browser will silently fail to parse the *entire* `<script>` block if it
hits one.
