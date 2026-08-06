# Animated Wave — Baking Plan

Addendum to `DESIGN_NOTES.md`, specific to turning the live wavy liquid surface (see `tank-gauge.html`, cylinder view) into pre-baked assets for the i.MX6 DualLite target.

## Frame count / frame rate

- The wave motion is slow and gentle — full smoothness at 60fps is wasted on the eye for motion this calm.
- Target **~10–12 fps**, **3–4 second loop** → **36–48 frames total**.
- Each frame is a small PNG; the whole loop should come in well under a couple hundred KB.

## Sync the two wave speeds before baking

- In the live prototype, the range's surface animates at **1.3× the speed** of the confirmed water's surface, and with a phase offset — a deliberate "out of sync, feels more uncertain" touch.
- That's fine for a live, infinitely-running animation, but it makes finding a clean loop point painful — the two waves only realign after a long time (not a short, bakeable cycle).
- **For the baked version, sync both surfaces to the same speed/phase relationship** so the whole scene completes exactly one clean cycle over the chosen frame count, and frame 0 matches frame N seamlessly (loops with no pop/jump).
- Trade-off: loses a bit of the "chaotic uncertainty" character between the two surfaces. Worth it for a trivially loopable asset — the visual difference is subtle enough not to matter much.

## Don't bake 5 full animated sequences — reuse the wave

The wave's shape and motion are identical regardless of which of the 5 sensor levels is active — only its **vertical position** changes. So instead of baking 5 complete animated tank sequences:

1. **Bake one small animated strip** of just the wavy surface line — transparent background, ~60×20px, 36–48 frames. This is the *only* thing that moves.
2. **Bake the tank body as 5 simple static images** (walls, caps, rim, reed-switch dots, threshold rings) — one per level (0/25/50/75/100%). These don't need to move, so no frames needed beyond one each.
3. **At runtime**, layer the animated strip on top of the correct static body image, positioned at the Y offset for whichever level is currently active.

This turns "5 levels × ~40 frames" into "~40 shared frames + 5 statics" — a large reduction in asset count and storage, while runtime cost stays the same as any other pre-baked approach: decode + blit, position the moving layer, done. No vector math, no gradients, no patterns computed on-device.

## Still applies from `DESIGN_NOTES.md`

- Keep `tank-gauge.html` as the **design source** for making further visual edits — bake from it, don't hand-edit the raster output.
- Rasterize with `rsvg-convert` / `resvg` at build time, not a browser screenshot pipeline.
- Keep the % (or later, liter) **labels as a separate lightweight text overlay**, not baked into any image — labels are the most likely thing to change once real liter calibration data comes in.
