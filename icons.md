# Icons

Generated, not hand-edited: `pip install cairosvg pillow`, then
`python design/make_icons.py` rewrites the PNGs below from
`design/artwork/Bavaria34/Cruiser 34 sida2-sails.svg` (Illustrator export of the sailed boat).
Transparent, hull edge to edge, rig cropped at the top; 16/32 px show the whole boat.
`apple-touch-icon.png` is opaque (`#1f2535`) with a margin: it is `maskable`, and iOS blackens transparency.

| File | Size | Used for |
|---|---|---|
| `webapp/favicon-16x16.png` | 16×16 | Browser tab favicon
| `webapp/favicon-32x32.png` | 32×32 | Browser tab favicon
| `webapp/apple-touch-icon.png` | 180×180 | iOS/PWA home-screen icon (`manifest.json`)
| `webapp/android-chrome-192x192.png` | 192×192 | PWA manifest icon; **also** the B&G/Navico app-tile icon (see `navico-app-announce.md`, `ICON_PATH` setting)
| `webapp/android-chrome-512x512.png` | 512×512 | PWA manifest icon (large)
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