# Signal K Setup — can1

How and why `signalk-server` is installed on the Pi, worked out in
conversation 2026-08-13. Companion to `signalk_alignment_plan.md` (which
covers this gateway's own REST API field naming — unrelated code path,
no overlap) and `architecture.md` (CAN/state-machine internals, also
untouched by anything here).

## 1. Decision

Run a standard `signalk-server` install on **`can1`**, a second SocketCAN
interface physically separate from `can0`. `can0` stays exclusively this
project's dedicated panel/relay-board CANopen bus (`architecture.md`);
`can1` is wired to the boat's actual NMEA 2000 backbone (GPS, depth, wind,
engine, battery data, etc.) and has no interaction with the CANopen
takeover/arbitration logic — Signal K reading `can1` is a completely
independent concern from this repo's gateway.

## 2. Why not Docker

Considered and rejected, for this specific box:

- SocketCAN devices aren't ordinary IP networking — a containerized
  `signalk-server` reaching `can1` would need `--network=host`, which gives
  up Docker's main isolation benefit while keeping all its friction. No real
  upside once you're on host networking anyway.
- Plugin development (the actual goal here — see §4) is a fast edit/restart
  loop built around `npm link`-ing a plugin directory straight into the
  server's `node_modules`. Through a container that becomes volume-mounting,
  host/container UID mismatches on written files, and `exec`-ing in for every
  `npm link`/install — friction with no payoff.
- `architecture.md` already states containerization was "not pursued for
  either deployment target" for the gateway itself; keeping Signal K
  bare-metal too keeps one operational model on this Pi instead of mixing
  containerized and non-containerized services.

## 3. Why npm/installer, not apt

No distro packages `signalk-server` — there's no maintained `.deb`. It's a
fast-moving, community-maintained Node.js app whose actual value is a live
plugin marketplace (installed/updated at runtime from the server's own admin
UI, npm underneath) — a model that doesn't fit apt's fixed-artifact,
distro-reviewed packaging at all. The project's own officially supported
install paths are: the installer script (npm underneath), Docker, or a
prebuilt Pi SD card image. No apt repo exists for any of them.

**Correction to the plan above** (found once actually installing, 2026-08-13):
there is no single `curl | bash` one-liner — that was a wrong guess, caught
before running anything, by checking the actual docs
(`github.com/SignalK/signalk-server/blob/master/docs/installation/
raspberry_pi_installation.md`) rather than trusting memory. The real sequence:

```
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo bash -   # NodeSource repo for Node 24
sudo apt install -y nodejs                                        # Node 24.19.0 (was 18.20.4)
sudo apt install -y libnss-mdns avahi-utils libavahi-compat-libdnssd-dev
sudo npm install -g signalk-server
sudo signalk-server-setup
```

`signalk-server` currently requires **Node.js ≥24 / npm ≥11** — the Pi's
stock Node (18.20.4, Debian's own package) had to be replaced via
NodeSource's apt repo first. Checked before upgrading: nothing else on this
Pi pinned Node 18 (no global npm packages installed; `venus-html5-app`'s own
`package.json` already wants `>=22` anyway), so no conflict.

**npm `allow-scripts` gotcha:** `npm install -g signalk-server` silently
skipped `@canboat/canboatjs`'s native-addon build script (npm 11's default
security posture blocks install scripts from the dependency tree unless
allowlisted) — without it, the compiled `canSocket.node` binding that lets
canboatjs open a raw SocketCAN socket is simply missing, so the NMEA 2000
connection would have failed at runtime with no obvious reason why. Fixed by
re-running with the exact packages npm itself named allowlisted:
`sudo npm install -g --allow-scripts=@canboat/canboatjs,es5-ext,storage-
engine,@serialport/bindings-cpp,@scarf/scarf,core-js signalk-server`.
Verified after: `build/Release/canSocket.node` present under
`@canboat/canboatjs`.

`signalk-server-setup` creates `~/.signalk/` as the config home (settings,
installed plugins) and registers `signalk.service`/`signalk.socket` — but see
§3.1 below, it could not actually be driven as intended in this session.

### 3.1 The setup wizard couldn't run interactively here

`signalk-server-setup` is a short TUI (`prompts` npm package) — config
directory, vessel name, MMSI, port 80 y/n, SSL y/n, then it writes
`settings.json`/`baseDeltas.json`/`package.json`/the startup script and (as
root) the two systemd units. It needs a real interactive TTY; running it
through this session's non-interactive shell just printed the first prompt
and exited without completing anything (confirmed: no `settings.json` was
produced by that attempt).

Rather than fight that with `expect`/`script` pty tricks (fragile, and any
mistimed keystroke risks writing a wrong systemd unit or vessel identity),
read the wizard's own source (`bin/signalk-server-setup`, plain readable JS)
and reproduced its file outputs directly and deterministically for the
intended answers:

- Vessel name: **Ävntyret** (correct spelling with the diacritic — Signal
  K's config is plain JSON/UTF-8, no reason to flatten it to the ASCII-safe
  `Aventyret` used for the MFD's avahi service name elsewhere)
- MMSI: **265043340** (the vessel's own — see the AIS aside below for how
  this was *not* found)
- Call sign: **SG4711** — not actually asked by the wizard (only name/MMSI
  are), added the same way via Signal K's standard
  `communication.callsignVhf` self path
- Port: **3000** (standard default, kept — see §3 above)
- SSL: off

`baseDeltas.json` was generated by requiring signalk-server's own
`dist/deltaeditor.js` `DeltaEditor` class directly (same class the wizard
itself uses) and calling `setSelfValue('mmsi', ...)`, `setSelfValue('name',
...)`, `setSelfValue('communication.callsignVhf', ...)`, `saveSync(...)` —
guaranteeing byte-identical delta shape to what the real wizard would have
produced, without needing the TTY. `settings.json`, the startup wrapper
script, and both systemd units were hand-written to match the wizard's own
templates verbatim (source read directly, not reconstructed from memory).

**One intentional deviation from the wizard's stock output:** added
`After=vbp-can1.service` / `Requires=vbp-can1.service` to `signalk.service`'s
`[Unit]` section — the wizard has no idea `vbp-can1.service` exists, but
without this, `signalk.service` could race it at boot and fail to open the
CAN connection on first try (mirrors this repo's existing
`vbp-gateway.service` ↔ `vbp-can0.service` pattern exactly).

**Own-vessel MMSI could not be sniffed off the bus.** Tried first, out of
curiosity, since the V60 (confirmed on the bus as `src=11`, a B&G
"Communication" class device) is also acting as an AIS receiver — it's
actively relaying *other* nearby vessels' AIS static data onto the N2K bus
(`candumpjs --pgn 129809`/`129810`, saw e.g. MMSI 265591790 "TUCANO", MMSI
265549420 "ABOAT II" during a 60s capture). That's other boats' identities,
not this vessel's own — own-ship MMSI only appears on N2K inside a DSC Call
Information frame (PGN 129808), which only transmits during an actual DSC
call/test, none of which happened during the capture window. User supplied
the real MMSI (265043340) and call sign (SG4711) directly instead.

## 4. Why this path, specifically because a plugin is planned

Chose "as standard an install as possible" deliberately: plugin-development
docs and community support assume the standard installer's layout
(`~/.signalk/node_modules`, `npm link` workflow, admin UI at `:3000`). Any
deviation from that (hand-rolled systemd unit for the server itself, Docker,
apt) would mean debugging against a setup nobody else's docs describe.

## 5. What this repo owns vs. what the installer owns

Split mirrors the existing `vbp-can0.service` / `vbp-gateway.service`
pattern:

- **`deploy/etc/systemd/system/vbp-can1.service`** (this repo, tracked) —
  oneshot, brings `can1` up at 250000 bitrate (NMEA 2000 standard, matches
  `can0`'s rate) before Signal K starts. The installer does **not** do this
  — it only installs/manages the `signalk-server` Node process, and knows
  nothing about kernel network interface state. Without this unit, `can1`
  stays down (`noop` qdisc, as found before setup) and Signal K's SocketCAN
  connection would fail to open.
- **`/etc/systemd/system/signalk.service` + `signalk.socket`** (installer-
  owned in spirit, not tracked in this repo — but see §3.1, actually
  hand-written this pass to match the installer's own templates exactly,
  plus the one deliberate `vbp-can1.service` ordering addition). Ordered
  after `vbp-can1.service` (`Requires=`/`After=` on the signalk side,
  `Before=signalk.service` on the can1 side — belt and suspenders), so the
  interface exists before Signal K tries to open it.
- **`~/.signalk/`** (installer-owned, not tracked here) — config, installed
  plugins. Turns out the NMEA 2000/SocketCAN connection pointed at `can1` is
  **not** part of `signalk-server-setup` at all (checked its source directly
  — the wizard only ever writes `pipedProviders: []`) — it's configured
  through the admin UI (Server → Data Connections → Add) after first login,
  a step still pending as of §6.

## 6. Status

**Installed and running, 2026-08-13.** `can1` up via `vbp-can1.service`
(confirmed live: `state UP`, `ERROR-ACTIVE`, 250000 bitrate, zero bus
errors) and real traffic verified two ways — the user's own `candump can1`,
and `candumpjs` (bundled with `@canboat/canboatjs`) decoding live PGNs from
it: position (`59.3504613, 18.8863914`), heading, rate of turn, attitude,
wind, rudder, speed, distance log, heartbeats, and other vessels' AIS static
data relayed by the V60 — real N2K traffic decoding correctly end to end.

`signalk-server` 2.30.0 running under `signalk.service`
(`systemctl status` confirms `active (running)`), serving `/signalk`
discovery unauthenticated as expected and returning `401` on
`/skServer/*`/`/signalk/v1/api/*` as expected (`tokensecurity` strategy is
on by default — matches Signal K's own documented standard behavior, not a
misconfiguration). Vessel identity set: name Ävntyret, MMSI 265043340, call
sign SG4711 (§3.1).

**Remaining, not yet done:**
1. First-login admin user creation via the browser (`http://<pi>:3000` →
   Login → create user) — inherently a manual, human, one-time step, not
   something to script.
2. Add the NMEA 2000/SocketCAN data connection pointed at `can1` via the
   admin UI's Data Connections page (§5) — this is what actually starts
   Signal K decoding `can1` into its own data model/API, as opposed to the
   passive `candumpjs` verification done so far, which bypassed
   `signalk-server` entirely.
3. Plugin development itself (§4) — not started.

## 7. Navico Gateway Clarification (2026-08-27)

Discovered: Signal K's current `settings.json` is configured to read from
`10.28.94.185:10110` (the B&G Zeus3 chartplotter) instead of the local `can1`.
The Zeus3 runs a Navico gateway that **converts NMEA 2000 to NMEA 0183 and
sends it over the network** — it is **send-only**, with no write capability.

**Decision:** Use the local `can1` interface directly instead. Reasons:
- Direct NMEA 2000 access (not downconverted to 0183)
- Bidirectional capability (read and write) — plugins can transmit to the bus
- Lower latency, fewer network dependencies
- Matches the original setup plan in §5

**Action:** Remove the Navico provider from `~/.signalk/settings.json`
(`pipedProviders`), then add a direct SocketCAN connection via the admin UI
(Server → Data Connections → Add → NMEA 2000 → SocketCAN, interface `can1`).
