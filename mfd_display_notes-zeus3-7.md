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
- Observed viewport **widths** (`window.innerWidth`), heights all 574px.
  There's also a collapsible autopilot pane, permanently docked to the
  left of the MFD's whole screen (separate from this app's own
  split-pane layout); "active area" below means whatever's left after
  the autopilot pane and other static MFD chrome. These four widths are
  a clean 2×2 grid — {app full-screen vs. app split into two panes} ×
  {autopilot collapsed vs. expanded} — not three-pane variants as
  previously guessed here:

  | Width | Autopilot pane | App layout |
  |-------|----------------|------------|
  | 803px | Collapsed      | Full screen, single pane (= active area total) |
  | 642px | Expanded       | Full screen, single pane (= active area total) |
  | 398px | Collapsed      | Split into two panes (~50/50, ~7px divider) |
  | 318px | Expanded       | Split into two panes (~50/50, ~6px divider) |

  Derivation: 803 − 2×398 = 7px divider; 642 − 2×318 = 6px divider — both
  pairs agree on a near-even 50/50 split with a ~6–7px gutter between
  panes, confirming the mapping. Expanding the autopilot pane costs
  **161px** of active area (803 → 642) — a real cost, but still a
  narrow sidebar, not a full pane ("still a thin thing" even expanded).

## Design takeaway

Design the Control view to remain usable down to **~318px wide** (worst
observed split), at a fixed **574px** tall. No HiDPI concerns. Avoid
ES2020+ syntax (`??`, `?.`) anywhere in shipped code — this MFD's
browser will silently fail to parse the *entire* `<script>` block if it
hits one.
