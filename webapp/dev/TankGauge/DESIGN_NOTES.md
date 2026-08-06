# Freshwater Tank Gauge — Design Notes

Context for `tank-gauge.html`, a prototype UI for a boat's freshwater tank level sensor. These notes capture decisions and *why* they were made, since they aren't obvious from the code alone.

## The sensor

- OEM part: **Bavaria water tank level sensor** (plastic rod, reed switches, 250mm/300mm variants depending on tank).
- Reports **4 discrete levels**: 0%, 25%, 50%, 75%, 100%. It is *not* continuous — a reading is the floor of a range, not an exact value.
- Confirmed (owner's own measurement, not yet done): will measure actual liters at each threshold later and swap the % labels for liter values. The interval logic doesn't change when that happens — only the labels.
- **0% does *not* mean empty or sensor fault.** Confirmed by the owner: treat a 0% reading as "level is somewhere between 0–25%," same as any other band. (An earlier draft treated 0% as an ambiguous fault/empty state with a warning UI — that was explicitly walked back. Don't reintroduce it unless the owner says otherwise.)
- 100% has no uncertainty above it (top switch = full).

## Vocabulary (use these terms, not synonyms)

- **Confirmed** — the portion of the tank the sensor guarantees has water (solid fill).
- **Uncertainty range** (or just **"range"** for short) — the band between the current threshold and the next one up, where the real level could be anywhere. Rendered as diagonal stripes.

## Two view modes

- **Flat panel** — a straight rectangular tank. Simple, no perspective distortion, arguably the more "honest" one to actually ship.
- **Cylinder** — a fake-3D cylindrical rendering (elliptical caps, gradient-shaded walls). **The owner prefers this one and it's the default view.** Flat panel is kept as a secondary option/reference, not the priority.

## Cylinder-specific fixes worth knowing about

- **Hatch pattern must be defined locally inside each `<svg>` root.** Originally the cylinder reused a `<pattern>` defined in the flat view's `<svg>` via `url(#hatchWater)` — cross-svg-root pattern references are unreliable across browsers and silently failed, rendering as transparent (showed up as a "black"/unfilled look, especially at the tank's rounded bottom cap). Fixed by giving the cylinder its own local pattern, `hatchWaterCyl`. **If you add more patterns/gradients later, always define them inside the same `<svg>` that uses them.**
- **Bottom cap ellipse** (`cylBaseCap`) is dynamically recolored to match whatever's happening at the very bottom of the tank (confirmed blue, or hatched if the 0% band is uncertain all the way down) — it used to be a static dark color and looked "empty" regardless of fill state.
- **Top surface of the uncertainty range** (`cylSurfaceUncertain`) is now filled with the same hatch pattern/angle as the walls (not just an outline), so it reads as a solid cap. A mirrored/cross-hatch angle was tried to make it read more clearly as a horizontal surface, but the owner preferred the matching angle — **don't reintroduce the mirrored angle.**
- **`SURFACE_NUDGE` constant (currently 14px)** — offsets the range's top surface visually below the threshold ring/label, so the two don't sit on top of each other and the range reads clearly as "up to around here." Purely cosmetic, easy to tune.
- Threshold marks (dashed rings + reed-switch dots) were deliberately thickened for visibility (ring/line stroke-width 2, dot stroke-width 2.5, dot radius 6).
- % labels sit on the **same side as the dots** (left side), not the opposite side, with a deliberately generous gap. Canvas `viewBox` was widened (`"-28 0 248 460"`) to make room for this without clipping.
- Threshold marker color: **brass** (`--brass` / `--brass-dim`), matching the rest of the panel's brass accents. A yellow variant was tried and explicitly rejected — don't reintroduce it.

## Target hardware constraint — this is the big one

- Runtime target is an **i.MX6 DualLite** embedded panel — dual Cortex-A9, weak Vivante GC880 GPU, immature `etnaviv` open driver. Live SVG rendering (patterns, unioned clip-paths, per-shape gradients, CSS transitions animating SVG attributes) is expensive on this class of hardware and risks janky/slow rendering.
- **Decision: don't ship the live interactive SVG.** Since there are only 5 discrete sensor states, **pre-render each state to a static raster (PNG)** ahead of time and just swap/crossfade images at runtime. Crossfading via opacity is cheap even on weak GPUs; animating vector geometry is not.
- Use `rsvg-convert` or `resvg` to rasterize at build time — not a browser screenshot pipeline.
- **Bake the reed-switch dots into each image** — no need to keep them as separate live elements since they're fully determined by which of the 5 states is showing.
- **Keep the % (or later, liter) labels as a separate lightweight text overlay, not part of the baked image** — labels are the one thing likely to change (once real liter calibration data comes in), and redrawing text is free, so there's no reason to re-bake images just for a label change.
- `tank-gauge.html` (the SVG/CSS/JS version) should be treated as the **design source** for making visual edits, not the thing that ships to the device.

## Known open item (not yet done)

- At the actual device window size, **802×573**, the full page content is currently ~1000px tall — meaning roughly the bottom 43% (the caption, the "Why this matters" note, part of the button row) gets cut off without scrolling. This was flagged but not yet fixed when work paused. Needs a layout pass — likely tightening the header/subtitle and padding, and/or a more aggressive side-by-side layout — before this is considered finished for the target screen.
