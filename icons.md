# Icons

Generated, not hand-edited: `pip install cairosvg pillow`, then
`python design/make_icons.py` rewrites the PNGs below from
`design/artwork/Bavaria34/Cruiser 34 sida2-sails.svg` (Illustrator export of the sailed boat).
Hull edge to edge, rig cropped at the top; 16/32 px show the whole boat and are transparent.
The 150/192/512 icons, the Navico tile and the Apple icon are opaque: Android paints transparent areas of
home-screen icons white, and iOS black. Only the favicons are transparent.
`apple-touch-icon.png` has a margin (`#1f2535`). It must not be `maskable` in `manifest.json`: Chrome then picks it
for the Android home screen and the launcher mask crops it; `android-chrome-maskable-512x512.png` is the one designed for that.

| File | Size | Used for |
|---|---|---|
| `webapp/favicon-16x16.png` | 16×16 | Browser tab favicon
| `webapp/favicon-32x32.png` | 32×32 | Browser tab favicon
| `webapp/apple-touch-icon.png` | 180×180 | iOS/PWA home-screen icon (`manifest.json`)
| `webapp/android-chrome-192x192.png` | 192×192 | PWA manifest icon (opaque, same picture as the Navico tile but with the original keel colour)
| `webapp/android-chrome-512x512.png` | 512×512 | PWA manifest icon (large)
| `webapp/navico-tile.png` | 192×192 | B&G/Navico app-tile icon (`ICON_PATH` in `navico-app-announce.md`). Opaque on purpose: Zeus shows an opaque icon as is, but zooms and shifts a transparent one
| `webapp/android-chrome-maskable-512x512.png` | 512×512 | Android home-screen icon (`purpose: maskable`): opaque plate. One UI (installed PWA) shows the central ~86% under a squircle, so the hull is lifted to clear the corners. Without it Android puts the transparent icons on white
| `webapp/mstile-150x150.png` | 150×150 | Windows tile icon (legacy)
| `webapp/garmin/icon.png` | 360×240 | Garmin MFD app-tile icon (`garmin/config.json`'s `icon` field, served to Garmin's `_garmin-mrn-html._tcp` avahi discovery)

Raymarine (and any other generic-avahi MFD browser) doesn't use a
dedicated icon field at all — it just reads the standard
`manifest.json`/favicon set above, same file as everything else. So
there's no separate Raymarine icon row.

## Android homescreen shortcut

When saving the webapp to an Android (including Samsung) homescreen, Chrome
prioritizes the manifest's Android-specific icons and uses
`android-chrome-512x512.png` (the largest one defined). If added as a
bookmark instead of a PWA install, it may fall back to the 192×192 version.
Either way, it picks from the Android icons in `manifest.json` rather than
the favicon or `apple-touch-icon.png`.
## B&G / Navico (Zeus3) tile

- Native tiles (`NOS/resources/bandg/panels/icons/*.png` in the MFD firmware) are 500×500 with the
  frame and shadow baked in: tile 360 px at (70, 11), 12 px black frame, picture in the 336 px square at (82, 23).
- Our icon is shown inside that frame. An **opaque** icon is shown whole, scaled to fit, so `navico-tile.png`
  is just the finished picture (keel lightened, sails dimmed: it is on the app's lightest blue,
  the day `--surface-hover`). A **transparent** icon was zoomed ~1.5x and shifted (fitted from one
  screenshot, 2026-10-05), which cropped the boat badly.
- Test a tile without touching the real one: a second announcer copy with its own `SOURCE_ID`, a **new
  URL** (Zeus ignores an announcement whose URL it already has) and the icon served from a spare port;
  the tile appears by itself within a minute. `/zeus-screenshot` grabs the result.
