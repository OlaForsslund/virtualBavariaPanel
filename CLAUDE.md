# CLAUDE.md — Virtual Bavaria Panel

CANopen gateway letting a Raspberry Pi act as a second control panel on a
yacht's shared panel/relay-board bus. Read these before touching code:

- `architecture.md` — design: takeover mechanism (§4), arbitration (§5), state machine (§6)
- `protocol_findings.md` — confirmed bus protocol; `panel_od_map.md` — panel OD sweep
- `dev-environment.md` — toolchain, repo layout, dev loops

## Hard constraints (hardware-verified 2026-07-19 — do not violate)

- The `1400:1` repoint dance (disable → set → enable) must run **back-to-back,
  no delays**: an RPDO-disabled window of ~150 ms drops ALL relays; <10 ms is fine.
- The gateway must already be **streaming the adopted state on `0x18C` before
  the repoint starts** (else relays blip off at switchover).
- Frames on `0x18B`/`0x18C` must alternate the **alive-toggle bit** (byte 0,
  bit 0) every frame or the board ignores the source. Not the NMT heartbeat —
  this bus has none (`1017` = 0).
- Changing `1400:1` in-place is rejected (abort `0x06090030`); same-value
  writes succeed. The repoint is **volatile** — board power cycle restores panel control.
- The panel cannot be commanded over the bus (confirmed, not just assumed —
  exhaustive probe 2026-07-26, `protocol_findings.md`: every writable object
  either ignores writes or is comms/PDO-parameter-only, none reach relay/
  button state); its display shows stale state while the gateway is active
  (architecture §1.1).
- `GatewayStateMachine` is **single-threaded**: only the runtime main loop may
  call it. Cross-thread hand-off is the lock-free `StreamBuffer` only. A future
  web interface must queue commands into the main loop, never call directly.

## Code layout

- `gateway/` — flat modules: `state_machine.py` (pure logic, no I/O),
  `runtime.py` (main loop + Streamer), `monitor.py`, `frames.py`,
  `constants.py`, `sdo_probe.py`, `takeover_experiment.py`, `config/`
- `simulators/` — pure cores (`relay_core.py`, `panel_core.py`) + bus shells
  (`relay_sim.py`, `panel_sim.py`, `node_base.py` incl. minimal expedited SDO server)
- `tests/` — all pure Python, run on any OS, no CAN stack needed

## Dev workflow

- Repo lives in WSL2 Ubuntu at `~/code/virtualBavariaPanel` (moved off the
  Windows filesystem 2026-07-19; `udp_multicast` needs Linux anyway). Venv at
  `~/venvs/vbp`; tests: `~/venvs/vbp/bin/python -m pytest tests/ -q`.
- Editing: VS Code WSL remote (`code .` inside Ubuntu). Run Claude Code from
  inside WSL too.
- Pi (`olaspi`, ssh key auth): clone at `~/virtualBavariaPanel` with its own
  `.venv`. Two modes, used depending on setting: (a) edit in WSL2 → `scp`
  changed files → run via ssh, git only for verified states; (b) working
  directly on the boat/Pi, edit and run in place at `~/virtualBavariaPanel`
  (this is how Claude Code runs when invoked on-boat). CAN bring-up command:
  dev-environment §6.
- The user commits and pushes themselves (lean messages); don't commit unasked.
- Hardware runs only with the user present; the monitor and sims are safe anywhere.

## Status after 2026-07-19 boat session

Hardware-verified end-to-end: glitch-free takeover, transparent panel
mediation (~50 ms panel→board), clean release, auto re-takeover watchdogs.
Panel cadence 25 ms. Simulators written with 10 core tests (35 total, green
on Windows).

## Status after 2026-07-19 WSL sim session

WSL2 Ubuntu up (venv at `~/venvs/vbp`; msgpack added to requirements,
needed by `udp_multicast`). All 35 tests green on Linux. Sim bus verified as separate processes: passive gateway decodes both
sims; `--activate` replay clean (abort on in-place write, disable dance,
no relay drop, clean release); kill/restart drill exercises watchdog +
auto re-takeover.

**Open finding from the drill:** on re-takeover after a board reboot,
`_try_repoint` adopts `board_bitmap` — the rebooted board's all-off state
if the gateway wins the race against the panel's next 25 ms frame (it did
in sim: repoint ~10 ms after boot). Previously-on relays then stay off for
the whole ACTIVE period (panel mediation is edge-triggered, so an unchanged
panel never re-asserts). architecture §6 doesn't specify which bitmap to
adopt here. Proposed fix (not yet decided): keep the gateway's own
`output_bitmap` when re-entering WAITING_FOR_BOARD *from ACTIVE*; adopt
board/panel state only on first activation.

**Status: deferred (2026-07-21), then resolved (2026-07-26)** — it bit.
User hard-power-cycled the Pi overnight (WiFi had dropped, no screen/
keyboard to fix in place) → no graceful shutdown/release → the board's
RPDO source vanished for ~32 min → the board's own supervision timeout
dropped all relays. On restart the gateway adopted `board_bitmap`
(all-off) while the panel switches still showed on — lights stayed off
with no fix short of re-toggling every switch. Fixed: `ActivatingState.
enter()` (`gateway/state_machine.py`) now adopts `panel_bitmap`, not
`board_bitmap` — the panel has memory (re-asserts switches across power
cycles), the board doesn't (defaults all-off on boot/timeout). The one
with memory dictates initial state. Also updated `architecture.md` §6;
test renamed to `test_adopts_panel_state_on_entering_activating`. Not yet
hardware-verified against a fresh takeover — next boat session should
confirm activation with panel/board bitmaps deliberately mismatched.

## Status after 2026-07-25 boat test & deploy session

Hardware-retested end-to-end with the REST API/webapp layer added since
2026-07-19: passive decode matches real panel/board state, takeover clean
(no relay blip), REST-originated circuit command reached the relay board,
panel button press still mediated correctly while active, release handed
control back to the panel cleanly (panel's stale button state re-asserted —
expected per architecture §1.1, not a bug).

**Open finding: Streamer idle cadence.** The `Streamer` thread
(`gateway/runtime.py`, `Streamer.run`) wakes at a fixed `stream_period`
(25 ms, ~40 Hz) unconditionally, forever — even in PASSIVE state with the
bus unpowered — just to check whether there's a bitmap to send. Raised
during a power-usage discussion before enabling boot auto-activation: not
currently a measured problem (idle wakeups here are a rounding error next
to the Pi's own baseline draw), but the streamer could back off to a
slower cadence when not actively streaming.
**Status: noted, not implemented** — low priority, revisit if it ever
matters in practice.

**Deployed with systemd, auto-start at boot.** Two units added
(`deploy/etc/systemd/system/`):
- `vbp-can0.service` — oneshot, brings up `can0` (`ip link set can0 down`
  first, ignoring failure, then `up` with the bitrate/params — needed to be
  idempotent against an already-up interface). `Before=vbp-gateway.service`.
- `vbp-gateway.service` — runs `gateway.main --activate` as user `ola`
  (no root needed — socketcan raw sockets don't require it), `Requires=`/
  `After=vbp-can0.service`, `Restart=on-failure`.

Fixed two bugs found while wiring this up (both hardware-verified via
`systemctl start/stop`, not just unit tests):
- `gateway/main.py` only caught `SIGINT` (Ctrl-C) for clean shutdown.
  `systemctl stop`/reboot send `SIGTERM`, which Python doesn't act on by
  default — so the `1400:1` release-on-shutdown would never have run,
  leaving the board pointed at a dead gateway (relays frozen until board
  power-cycle) on every service stop/restart. Added a `SIGTERM` handler
  (`runtime.request_shutdown()`) that routes into the same shutdown path.
- `runtime.py` `shutdown()`'s best-effort-release warning referenced a
  bare `state` name instead of `self.sm.state` (would have crashed that
  one edge-case branch — interrupted mid-`ACTIVATING` — instead of
  releasing).

**`eth0` DHCP server for the MFD network.** The MFD (B&G Zeus3, discovers
apps via UDP multicast announce on `239.2.1.1:2053`, see
`mfd-app-announce.service`) expects a DHCP server on its network segment;
previously an external router provided this, but the Pi is now plugged
directly into that segment via `eth0`. Fixed via NetworkManager (already
manages `eth0`) rather than a standalone dnsmasq service, since NM already
owned the interface: `nmcli connection modify "Wired connection 1"
ipv4.method shared` — this makes NM assign `eth0` a static address
(auto-picked `10.42.0.1/24`) and run its own dnsmasq instance for
DHCP+DNS on that interface only. Two gotchas along the way:
- A stale `/etc/dnsmasq.d/temp-dhcp.conf` (leftover from an earlier,
  never-actually-working attempt — `192.168.50.x` range, no static IP on
  `eth0` so it couldn't serve correctly) was holding port 67 system-wide.
  Removed.
- The system's main `dnsmasq` binds one wildcard `0.0.0.0:53` socket by
  default, which then collided with NM's per-connection instance once
  `eth0` had an address. Fixed with `/etc/dnsmasq.d/exclude-eth0.conf`
  (`bind-dynamic` + `except-interface=eth0`) so the system dnsmasq binds
  per-interface and skips `eth0` entirely, leaving it exclusively to NM.

**MFD app was stuck on "loading" — found and fixed.** Not a network or
browser-compatibility issue (confirmed via a temporary diagnostics page +
error beacon, see below): the MFD's browser (`QtWebEngine/5.12.9`,
Chromium 69) fully supports the ES2017 syntax the app uses (async/await,
arrow functions, template literals, destructuring, classes, spread,
fetch) and successfully fetched `/status` live. The actual bug was one
`??` (nullish-coalescing, ES2020) in the Config-tab code
(`webapp/index.html`, in `renderConfigOnce`) — Chrome 69 predates ES2020
and throws a `SyntaxError` on it, and since a syntax error anywhere in a
`<script>` block prevents the *entire* block from parsing, this one line
silently blocked everything below it, including the `poll()` call that
populates the Control view. Fixed by swapping `?? new Set(...)` for
`|| new Set(...)` (equivalent here since `getVisibleSet()` only ever
returns `null` or a `Set`, and a `Set` is always truthy regardless of
size).

Diagnostic method, in case this class of bug recurs: announced a second,
temporary MFD app tile (separate `Source` ID, own small standalone
announcer script, not installed as a service) pointing at a plain
ES5-only diagnostics page, which beacons its results (`navigator.userAgent`,
feature-detection via `new Function()` + try/catch, live `fetch`/`XHR`
tests) back to a tiny logger via `<img src>` beacon rather than requiring
anyone to transcribe MFD screen text. Also temporarily added a global
`window.onerror`/`unhandledrejection` handler to the real app that beacons
the same way — that's what actually caught the `??` SyntaxError with an
exact file:line:col. **The `onerror` beacon is still live in the deployed
`/var/www/html/index.html` (kept intentionally, per-request, as a safety
net for now) but was NOT carried into the committed `webapp/index.html`**
— it's throwaway debug instrumentation (hardcoded to a scratch port), not
real app code.

**Found and fixed significant repo/deployment drift.** The live
`/var/www/html/index.html` (lighttpd's actual docroot — separate from this
repo's `webapp/` dir; deployed files are hand-copied, not symlinked) had
diverged substantially from the committed `webapp/index.html`: dark theme
matching the Zeus3's own chrome, tabbed Control/Diagnostics/Config UI,
per-circuit visibility config persisted in `localStorage`, ETag-aware
polling — none of it was ever committed. Copied the live version (minus
the throwaway `onerror` beacon above) back into `webapp/index.html` so
it's finally tracked. `manifest.json`/`sw.js` were already identical
between the two, no drift there. Backend note: the frontend's ETag/
`If-None-Match` conditional-polling logic is currently a no-op — 
`gateway/web.py`'s `/status` handler doesn't set an `ETag` header, so
`lastEtag` never populates and every poll is a full 200. Not a bug (harmless),
just an unfinished optimization; worth wiring up the `ETag` header if this
ever needs to matter for bandwidth.

## Next steps

1. Add `--script` timed-press option to panel_sim for automated integration
   tests (proposed, not yet confirmed with user); then a pytest integration
   module spawning sims as subprocesses (skip on native Windows).
2. EDS files promised in docs but sims hand-roll SDO — decide: author EDS or
   amend docs. Venus OS deployment later.
3. Possible open-sourcing: keep the private analysis repo unnamed in all docs.
4. **Simplify lighttpd to pure reverse proxy.** Currently lighttpd serves
   `webapp/` itself from a hand-copied `/var/www/html` docroot and only
   proxies API paths (`deploy/etc/lighttpd/conf-available/20-vbp-proxy.conf`,
   `^/(status|circuits|sensors|ws)`) to uvicorn on `127.0.0.1:8000` — but
   uvicorn already serves the webapp too (`gateway/web.py`'s `StaticFiles`
   mount, used by `run_hardware.sh`). lighttpd's only real job is holding
   privileged port 80; the static-serving duplication is what caused the
   repo/deployment drift bug (2026-07-25 session). Fix: make lighttpd proxy
   *everything* unconditionally —
   ```lighttpd
   server.modules += ("mod_proxy")
   proxy.server = ( "" => (( "host" => "127.0.0.1", "port" => 8000 )) )
   ```
   — then drop the `/var/www/html` hand-copy; the repo's `webapp/` becomes
   the single source of truth in every run mode. Not yet applied — user
   wanted to commit other pending changes first and investigate something
   else before circling back.
