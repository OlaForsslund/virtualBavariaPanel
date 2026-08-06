# Signal K Alignment — Plan

Context and reasoning for why/how this gateway's REST API is moving toward
Signal K's vocabulary, worked out in conversation 2026-08-07. Companion to
`architecture.md` (which this doesn't change — CAN/state-machine internals
are untouched by anything here).

## 1. Decision

Align field *names and value conventions* in the REST API with the Signal K
data model now. Do **not** adopt Signal K's wire protocol (delta/update
envelope, WebSocket subscribe, PUT request/response) yet, and do not run
`signalk-server` yet.

**Why now:** cheap — it's mostly renaming JSON keys, no new dependency, no
architecture change. It gives a head start on two possible future moves
without committing to either:
- A Signal K *plugin* (thin adapter: this gateway's REST → `app.handleMessage`
  deltas + a PUT handler that calls back into this gateway's existing
  command path) — becomes closer to a relabeling exercise.
- A frontend that consumes real Signal K instead of this gateway's REST
  directly — the paths it already learned don't change, only the transport
  would.

**Why not the full protocol yet:** the delta envelope (`context`/`source`/
`timestamp` per value) only pays off once something is actually running the
subscribe/dispatch machinery (`signalk-server`). Replicating that shape in
our own REST API ahead of time buys nothing — no real client can subscribe
to it either way — it would just be ceremony. That machinery comes free the
moment a real plugin is written against a real server; no reason to hand-roll
it now.

## 2. Why not go straight to signalk-server + a real plugin

- The genuinely novel/hard part of this project — the CANopen takeover,
  arbitration, and state machine (`architecture.md` §4–6) — gets *zero*
  simplification from Signal K either way. It stays exactly as-is regardless
  of this decision.
- Roughly half the current API (`/calibration/battery`, `/config`,
  `/diagnostics`, `/system/restart`) has no Signal K equivalent and stays
  bespoke no matter what — these are appliance/admin concerns, not boat data.
  (`/config` has a plausible future home in Signal K's *Application Data API*,
  but that's gated behind turning on Signal K's security/auth layer — real
  infrastructure this single-boat app doesn't otherwise need. Revisit only if
  auth becomes desirable for other reasons, e.g. gating relay control.)
- `signalk-server` as a hard runtime dependency for basic relay control is a
  real robustness regression worth avoiding until there's a concrete reason
  to accept it — right now, if the gateway is up, relay control works, full
  stop.

## 3. MFD browser — checked, not a blocker for going further later

Investigated because a past bug looked network-related. It wasn't:
`QtWebEngine/5.12.9` (Chrome 69) fully supports WebSocket (has since Chrome
4) — the "stuck on loading" bug was one ES2020 `??` breaking the whole
`<script>` block's parse, unrelated to networking (see CLAUDE.md). The
`mod_proxy` in front of uvicorn (`20-vbp-proxy.conf`) can tunnel WebSocket
transparently on lighttpd ≥1.4.46; installed version here is 1.4.69. So a
future move to subscribe-over-WebSocket is viable whenever it's wanted — the
poll-with-a-timer the webapp does today is a choice, not a constraint. The
one carried-forward constraint either way: **no ES2020+ syntax** (`??`,
`?.`) anywhere in `webapp/` — bit us once already.

## 4. Field renames — step 1 (this pass)

Only touches `gateway/web.py`, `webapp/index.html`, `tests/test_web.py`.
Nothing in `gateway/state_machine.py`, `runtime.py`, or the CAN layer.

### `GET /status` — circuits

| Before | After |
|---|---|
| `circuits: { "ANCHOR": bool, ... }` | `electrical: { switches: { "ANCHOR": { state: bool }, ... } }` |

Matches Signal K's real shape one level deeper (`electrical.switches.<id>.state`)
without adopting the delta envelope. `state`/`streaming`/`output_bitmap`/
`panel_bitmap`/`board_bitmap` are internal gateway/CANopen debugging fields
with no Signal K equivalent — left untouched.

### `GET /sensors` — battery voltage

| Before | After |
|---|---|
| `starter_voltage`, `house_voltage` | `electrical: { batteries: { starter: { voltage }, house: { voltage } } } }` |

### `GET /sensors` — tanks: **deferred, not part of this pass**

`freshwater_level`/`freshwater_liters`/`blackwater_level`/`blackwater_liters`
stay exactly as they are for now. Signal K wants `tanks.freshWater.0.
currentLevel` as a 0–1 ratio of total capacity — this gateway has no single
capacity figure (tank cross-section isn't uniform, `calibration.py` stores
per-level liters directly, confirmed non-proportional: 38L/31L/45L across
three quarters of the same tank). Renaming this requires deciding first,
not silently: either add a nominal capacity and accept the ratio is
approximate, or keep reporting liters directly and accept tanks stay
non-standard. **Open — decide separately, not folded into this pass.**

### `POST /circuits/{name}` — endpoint path/shape: unchanged in this pass

This is a URL-routing/transport question (Signal K's real equivalent is a
`PUT` to the value's own path), not a data-naming one — out of scope for
"rename the fields that come from the CAN blob." Revisit once/if the
transport itself moves toward Signal K's PUT semantics.

## 5. Future consideration: `navigation.lights`

Checked the spec for a controlled vocabulary of switch/circuit names
(`electrical.switches.<id>`) — there isn't one, `<id>` is free-form (same
pattern as `electrical.batteries.<id>`), which confirms keeping the Bavaria
names as switch IDs (§4) needs no further justification.

But the spec does define `navigation.lights`, a single enum describing which
COLREGs light configuration the vessel is currently showing — a different
abstraction than per-relay state:

```
navigation.lights: "off" | "anchored" | "sailing" | "motoring" |
                    "not-under-way" | "fishing" | "towing < 200m" | ...
                    (22 values total)
```

This lines up well with what the essentials UI already does conceptually:
"Navigation lights" (bow+aft) ≈ `"sailing"`, "Anchor light" ≈ `"anchored"`,
bow+aft+steaming together ≈ `"motoring"`. Deriving it from the four light
relays is real logic, not a rename (needs a fallback for combinations that
don't cleanly match a COLREGs mode, e.g. `"off"` or `"fault"`) — noted here
as a candidate feature, not part of this pass.

## 6. Explicitly out of scope (this document, and this pass)

- Delta/update envelope, `context`/`source`/`timestamp` — not until a real
  plugin exists.
- `signalk-server`, the plugin itself, WebSocket subscribe — later,
  independent decisions, not blocked by anything found so far (§3).
- `/calibration`, `/config`, `/diagnostics`, `/system/restart` — stay
  bespoke; `/config` might move to Signal K's Application Data API later
  *if* security/auth is adopted for other reasons.
- Victron BLE integration into this gateway/plugin — separate track,
  prototyped independently in `~/victronReadout`. Revisit once this pass is
  settled.
