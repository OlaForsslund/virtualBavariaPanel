# Virtual Bavaria Panel — Development Environment

## 1. Toolchain

- **OS:** Windows host; the local dev loop runs inside **WSL2 (Ubuntu)**,
  because python-can's `udp_multicast` backend is not supported on native
  Windows. Git Bash on the host for general shell/git operations.
- **Editor:** VS Code, with Python, WSL, and Remote-SSH extensions
- **Language:** Python 3.11+
- **Key packages:** `python-can`, `canopen`, `fastapi`, `uvicorn[standard]`,
  `pyyaml`, `pytest`
- **Version control:** Git

## 2. Repo Structure

```
/gateway
  main.py
  /panel_interface
  /relay_interface
  /web_interface
  /state_machine
  /config

/webapp

/simulators
  panel_sim.py
  relay_sim.py
  /eds              <- shared object dictionaries (gateway + simulators)

requirements.txt
```

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

All steps run inside WSL2:

1. Run `relay_sim.py` (virtual bus) — acts as relay board node.
2. Run `panel_sim.py` (virtual bus) — acts as control panel node.
3. Run `gateway/main.py` (virtual bus) — mediates between the two, serves
   the web interface.
4. Drive the web app or trigger panel_sim button presses; confirm state changes
   propagate correctly — including the arbitration cases (web overrides
   panel, panel toggle overrides web; see `architecture.md` §5).

## 6. Hardware Validation Loop

- Use VS Code Remote-SSH to open the repo directly on the Pi (Ubuntu or
  Venus OS).
- Swap config to `socketcan` / real channel.
- Run the gateway against the real panel and/or relay board in place of
  the simulators — no code changes required.

## 7. Testing Strategy

- **Unit tests** — pure domain/state-machine logic, no CAN bus involved.
  Fast, run anywhere, including CI.
- **Integration tests** — gateway running against `panel_sim`/`relay_sim`
  over the virtual bus. Exercises real CANopen encoding, object dictionary
  lookups, and PDO/SDO flows end-to-end, including takeover
  (`1400:1` remap), release, and arbitration scenarios.
- **Hardware validation** — manual/periodic runs against real panel and
  relay board via the hardware validation loop above.
