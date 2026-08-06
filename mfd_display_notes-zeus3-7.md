# MFD Display Capabilities — B&G Zeus3 7

Captured 2026-07-25 on the boat, via a temporary `window.onerror` +
dimension-reporting beacon added to `webapp/index.html` (see CLAUDE.md,
"MFD app was stuck on 'loading'" for how/why). For offline UI design —
lets you size mockups without the physical MFD in hand.

## Device / browser

- Model: B&G Zeus3 7 (`mfd_model_detail=Zeus3 7` in the app-launch query
  string; `mfd_name` is the boat's own MFD hostname, "Aventyret")
- Full launch query string, as observed in lighttpd's access log referer
  field (`GET /status`, 2026-08-06):
  `?mfd_name=Aventyret&mfd_model_detail=Zeus3%207&lang=en&mode=day&brand=B%26G`
  — `lang`/`mode`/`brand` not currently read by `webapp/index.html`, but
  available if the app ever wants to adapt (e.g. `mode=day`/`night`
  theming).
  **TODO / idea:** `mode` looks like it tracks the MFD's own day/night
  display setting (dims/inverts other native screens at night) — worth
  listening to this in the future to switch the webapp's own theme
  in sync, so it isn't a bright white/day page on an otherwise
  night-dimmed helm. Not yet confirmed whether it updates live if the
  MFD's mode changes while the app is already open, or only at launch.
- Browser: `QtWebEngine/5.12.9`, Chromium 69 (`Chrome/69.0.3497.128`)
  — fully supports ES2017 (async/await, arrow fns, template literals,
  destructuring, classes, spread, `fetch`). Does **not** support ES2020+
  (`??`, `?.` throw a `SyntaxError`. See CLAUDE.md for the bug this caused.)
  Verbatim `navigator.userAgent`, confirmed 2026-08-06:
  `Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/5.12.9 Chrome/69.0.3497.128 Safari/537.36`
- No service worker support surfaced (`'serviceWorker' in navigator` false)
  — expected, the app is served over plain HTTP and service workers
  require a secure context.
- `devicePixelRatio: 1` — design at 1:1 pixel ratio, no HiDPI scaling.
- Not sandboxed: `window === window.top`, `location.origin` is a real
  origin (not opaque/`null`), same-origin `fetch`/`XHR` work normally.

## Screen / viewport

- Physical screen: **1024 × 600** (`screen.width`/`screen.height`,
  constant regardless of app layout).
- MFD chrome overhead is a constant **26px of height**.
- The app area can be split in half vertically and horizontally for up to
  4 simultaneous views. In addition, the autopilot pane can enter from the
  left, further limiting the available horizontal space.
- Full viewport is 574px tall. When split, it becomes 284px tall (borders
  eat the rest).
- It's possible to make other split ratios, but we won't design for those
  when testing layouts.
- Along the horizontal axis, the regions are:

  | Region | Width | Notes |
  |---|---|---|
  | Sidebar/borders | 50px | fixed |
  | Autopilot pane | 0–161px | collapsible to 0 |
  | App area | remainder | splittable, up to 4 panes |
  | Data pane/borders | 171px | fixed |

- Table below shows effective horizontal viewports

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

Design the Control view to remain usable down to **~318px wide, ~284px
tall** (worst-case quarter split, autopilot expanded). No HiDPI concerns.
Avoid ES2020+ syntax (`??`, `?.`) anywhere in shipped code — this MFD's
browser will silently fail to parse the *entire* `<script>` block if it
hits one.

At quarter size, usability is inherently limited — screen real estate and
finger size don't shrink with the layout. Don't try to cram full
functionality in there; favor a reduced/essentials-only view (as Control
already does with its separate Essentials tab) over squeezing every
control into a quarter pane.
