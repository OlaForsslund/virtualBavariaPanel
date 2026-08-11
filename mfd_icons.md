# Icons

| File | Size | Used for |
|---|---|---|
| `webapp/favicon-16x16.png` | 16×16 | Browser tab favicon
| `webapp/favicon-32x32.png` | 32×32 | Browser tab favicon
| `webapp/apple-touch-icon.png` | 180×180 | iOS/PWA home-screen icon (`manifest.json`)
| `webapp/android-chrome-192x192.png` | 192×192 | PWA manifest icon; **also** the B&G/Navico app-tile icon (`mfd-app-announce.py`'s `ICON_PATH`)
| `webapp/android-chrome-512x512.png` | 512×512 | PWA manifest icon (large)
| `webapp/mstile-150x150.png` | 150×150 | Windows tile icon (legacy)
| `webapp/garmin/icon.png` | 360×240 | Garmin MFD app-tile icon (`garmin/config.json`'s `icon` field, served to Garmin's `_garmin-mrn-html._tcp` avahi discovery)

Raymarine (and any other generic-avahi MFD browser) doesn't use a
dedicated icon field at all — it just reads the standard
`manifest.json`/favicon set above, same file as everything else. So
there's no separate Raymarine icon row.