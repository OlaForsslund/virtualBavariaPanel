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

### `GET /sensors` — tanks: **resolved 2026-08-07, no longer deferred**

Was blocked here on a wrong assumption, corrected after actually checking
the schema: `currentLevel` ("Level of fluid in tank 0-100%", units
"ratio") has **no required relationship to `capacity`** — they're separate,
independent, both-optional properties. So there was never a need for a
nominal capacity figure; `currentLevel` is just the sender's own reading,
unit-converted. Implemented as `tanks.freshWater.currentLevel` /
`tanks.blackWater.currentLevel` = `snapshot.*_level / 100` — exact for the
rod/float sensor's fixed 0/25/50/75/100 steps, no precision loss. The
liters conversion (`calibration.tank_liters()`, previously computed here)
moved client-side (`webapp/index.html`'s `tankLiters()`), reading the same
per-level calibration table the Sensor calibration form already edits —
`calibration.tank_liters()` itself is untouched, still tested, just no
longer called from this handler.

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
- `signalk-server`, the plugin itself — later, independent decisions, not
  blocked by anything found so far (§3). WebSocket subscribe is designed
  (§7) but not yet implemented.
- `/calibration`, `/config`, `/diagnostics`, `/system/restart` — stay
  bespoke; `/config` might move to Signal K's Application Data API later
  *if* security/auth is adopted for other reasons.
- Victron BLE integration into this gateway/plugin — separate track,
  prototyped independently in `~/victronReadout`. Revisit once this pass is
  settled.

## 7. WebSocket subscribe — implemented 2026-08-07

`gateway/web.py`'s `/subscribe` + `webapp/index.html`'s `connectSubscribe()`.
Hardware-verified live on the boat: initial full dump on connect, exactly
one delta per actual change (checked via `/circuits/RESERVED1` toggle,
reverted after), gateway restart mid-session glitch-free (relay state
unchanged across restart, matching the earlier field-rename verification).

One scope call made while implementing, not decided in advance: the WS
stream includes `electrical.batteries.*` deltas (server-side, cheap, and
proven ready for a future Victron source at the same path — see the
multiple-sources note below), but the webapp doesn't apply them yet — the
sensors sidebar still uses its own REST poll (`pollSensors`, unchanged),
since that data only refreshes server-side every `SENSOR_POLL_PERIOD` (5s)
regardless of transport, so WebSocket buys no latency win there. Tanks
were never part of the WS stream (§4's deferred decision still applies) and
still poll via REST only.

**Decision: the gateway's own WebSocket speaks a subset of Signal K's real
wire protocol** (subscribe message + delta message shapes), not a bespoke
push format. Reasoning, since it reverses the earlier "don't build the
envelope ahead of a real consumer" stance (§1): that caution applies when
*nothing* would actually consume the shape yet. Here the consumer is real
and immediate — our own webapp — so replicating the wire shape has an
immediate payoff: one client-side function serves both this gateway (relay/
tank/panel-battery data, forever — that data never moves to `signalk-server`)
*and* a real `signalk-server` later (Victron data, once the plugin exists),
differing only by URL and which paths are subscribed to. Scoped to just
what the webapp needs — one context (`vessels.self`), flat path/value
deltas — not the full spec (multi-vessel, metadata registration,
notifications).

**Reconnection is the client's job, not the protocol's.** Plain
`WebSocket` has no auto-retry. Required on `onclose`/`onerror`:
retry after a short delay, re-send the subscribe message (a new connection
remembers nothing), and re-fetch a full REST snapshot before trusting deltas
again — deltas only carry *changes*, so anything that changed during the
disconnected gap is otherwise silently missed. True regardless of which
server it's talking to.

**Multiple sources for the same path — real for us, not hypothetical.**
Both the panel's own sensor and (once integrated) the Victron SmartShunt
report house battery voltage. Signal K's answer, confirmed against the
spec: same path, not separate paths. The full/REST model keeps every
source's value under a `values` object keyed by source id, with a top-level
`value`/`$source` showing whichever one is currently "selected" (most
recent by default). Over the delta stream this arrives as **separate
messages**, each tagged with its own `source` — so naively doing
`state[path] = value` on every incoming delta means the last one to arrive
silently wins, flapping between two readings depending on timing rather
than a deliberate choice. Two ways to handle it, decide when Victron
integration actually happens: (a) subscribe to one specific source only
(spec supports `path.values[sourceId]` addressing, so the server does the
filtering), or (b) receive both and let the webapp choose which to display.
Leaning (a) — simpler client code, decision made once at subscribe time
instead of on every message.

## 8. Faster sensor polling + tanks over WebSocket — implemented 2026-08-07

Prompted by wanting near-real-time tank readings for manual tank
measurements (2026-08-08). Hardware-verified live:

- `/subscribe` now includes `tanks.*` deltas (`_tank_values()` in
  `gateway/web.py`), and the webapp actually consumes them now (unlike
  `electrical.batteries.*`, which was sent-but-unused per §7) — with
  polling at 1s instead of 5s, the "WebSocket buys no latency win" argument
  that justified deferring sensors-over-WS no longer holds, so both
  batteries and tanks were wired into `applyDelta`/`renderSensors` at the
  same time. `pollSensors()`'s standalone REST timer is gone; `/sensors`
  is now REST-for-initial/reconnect-snapshot + WS-for-live-updates only,
  matching switches' pattern exactly.
