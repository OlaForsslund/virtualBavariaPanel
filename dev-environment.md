# Virtual Bavaria Panel — Development Environment

## 1. Toolchain

- **OS:** Windows host; the repo and the whole dev loop live inside
  **WSL2 (Ubuntu)** at `~/code/virtualBavariaPanel` — python-can's
  `udp_multicast` backend is not supported on native Windows, and the
  Linux filesystem is much faster than `/mnt/c`. Venv at `~/venvs/vbp`.
- **Editor:** VS Code, with Python, WSL, and Remote-SSH extensions
- **Language:** Python 3.11+
- **Key packages:** `python-can`, `canopen`, `fastapi`, `uvicorn[standard]`,
  `pyyaml`, `pytest`
- **Version control:** Git

## 2. Repo Structure

```
/gateway
  main.py             <- entry point
  constants.py        <- bus constants (from protocol findings)
  frames.py           <- relay-state frame encode/decode
  monitor.py          <- passive bus decoder
  state_machine.py    <- gateway state machine (pure logic, architecture.md §6)
  runtime.py          <- main loop wiring state machine to the bus; Streamer
  sdo_probe.py        <- read-only SDO hardware probe
  takeover_experiment.py
  /config

/webapp

/simulators
  panel_sim.py
  relay_sim.py
  /eds              <- shared object dictionaries (gateway + simulators)

/tests
requirements.txt
```

Components start as flat modules; a module becomes a package directory
only when it actually grows multiple files (web_interface likely will).

## 3. Config Strategy

- All environment-specific values (CAN interface type, channel, bitrate,
  web port, log level) are read from environment variables, with sensible
  defaults for local development.
- Local dev default: `interface: udp_multicast` — python-can's cross-process
  virtual bus (Linux/WSL2 only). Plain `virtual` only connects `Bus`
  instances within a single Python process; since the gateway and both
  simulators run as separate processes here, `udp_multicast` is needed for
  them to see each other's traffic. A single multicast group mirrors the
  single shared physical bus.
- Pi/Venus OS: `interface: socketcan`, real channel (e.g. `can0`). One
  interface only — there is only one bus.
- COB-IDs and node IDs are shared constants between gateway and simulators,
  kept alongside the EDS files and sourced from `protocol_findings.md`. The
  one value that is a project choice rather than a finding is the gateway's
  own TPDO COB-ID, `0x18C`.
- No code changes required to move between environments — only config
  values change.

## 4. Simulators

- **panel_sim** — acts as CANopen node 11 standing in for the physical
  control panel. Produces the confirmed relay-state frame on TPDO `0x18B`
  (see `protocol_findings.md`), triggered by button presses. As the real
  panel cannot update its internal state from externally originated
  changes, neither does the simulated one. Can be driven manually
  (CLI/keyboard) to trigger button presses during development and tests.
- **relay_sim** — acts as CANopen node 21 standing in for the physical
  relay board. Holds relay state internally and implements the confirmed
  board behavior (`protocol_findings.md`, `architecture.md` §4): toggle-bit
  gating, `0x20B` confirm, live `1400:1` repoint, volatile revert on
  restart.
- Both simulators reproduce the captured startup behavior (`startup2`, see
  `protocol_findings.md`): boot-id frame, one-shot NMT boot-up
  (`0x70B` / `0x715`), straight into Operational, TPDO streaming from boot —
  no periodic heartbeat. panel_sim also re-asserts a remembered state
  shortly after boot, so the gateway's startup adoption can be tested.
- Both use the shared EDS files under `/simulators/eds` to stay consistent
  with the gateway's object dictionary expectations.

## 5. Local Dev Loop

Shortcut: `./run_simulated.sh` starts all three (relay_sim + gateway
backgrounded, panel_sim in the foreground since it's the interactive one) and
tears them all down on Ctrl-C. Use the manual per-terminal version below when
you need to watch/restart one piece independently (e.g. killing just the
gateway to test the re-takeover watchdog).

Open a terminal, `cd` into the repo, and run `./run_venv.sh` to activate the
venv — do this in every terminal below before its command.

- **Terminal 1 — relay board:** `python -m simulators.relay_sim`
- **Terminal 2 — control panel:** `python -m simulators.panel_sim`
  (type a relay name + Enter to simulate a button press)
- **Terminal 3 — gateway:** `python -m gateway.main --activate`
  (drop `--activate` for passive/observe-only)
- **Terminal 4 — bus traffic (optional):** `can_viewer -i udp_multicast -c 239.74.163.2`
  — python-can's built-in live viewer, not a custom tool

Then drive the web app or trigger panel_sim button presses; confirm state
changes propagate correctly — including the arbitration cases (web overrides
panel, panel toggle overrides web; see `architecture.md` §5).

- **Terminal 5 (optional) — MFD layout preview:** with the gateway running,
  open `http://localhost:8000/dev/zeus3_7_preview.html`. It's a harness, not
  part of the app itself (kept under `webapp/dev/`, a subfolder, so it's
  obviously separate from what ships as the actual UI): an iframe pointed
  at the running app's own URL (editable, defaults to same-origin), pinned
  to one of the Zeus3 7's confirmed split-screen widths
  (`mfd_display_notes-zeus3-7.md`) at 100% zoom — no `transform: scale`, so
  it's a true pixel-accurate preview, not an emulation. Use it to design/
  check the webapp's layout at each split width without needing the MFD or
  boat.

## 6. Hardware Validation Loop

- Use VS Code Remote-SSH to open the repo directly on the Pi (Ubuntu or
  Venus OS).
- Bring up the interface:
  `sudo ip link set can0 up type can bitrate 250000 restart-ms 1000 berr-reporting on fd off`
- Swap config to `socketcan` / real channel (`VBP_CAN_INTERFACE=socketcan`,
  `VBP_CAN_CHANNEL=can0`).
- Run the gateway against the real panel and/or relay board in place of
  the simulators — no code changes required.

## 7. Redeployment Workflow

Once the gateway is deployed to a Pi with systemd, the iterative dev workflow
is:

```
sudo systemctl stop vbp-gateway.service
# Update code (git pull, copy files, etc.)
sudo systemctl start vbp-gateway.service
```

If you've modified the systemd unit files themselves, also run:

```
sudo systemctl daemon-reload
```

You don't need to restart `vbp-can0.service` — the CAN interface stays up.

For webapp frontend changes (`webapp/`), you also need a hard refresh in your
browser to clear any cached assets.

## 8. Testing Strategy

- **Unit tests** — pure domain/state-machine logic, no CAN bus involved.
  Fast, run anywhere, including CI.
- **Integration tests** — gateway running against `panel_sim`/`relay_sim`
  over the virtual bus. Exercises real CANopen encoding, object dictionary
  lookups, and PDO/SDO flows end-to-end, including takeover
  (`1400:1` remap), release, and arbitration scenarios.
- **Hardware validation** — manual/periodic runs against real panel and
  relay board via the hardware validation loop above.
