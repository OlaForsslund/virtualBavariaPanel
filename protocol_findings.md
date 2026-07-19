# Bavaria Panel CAN Protocol

The bus is **CANopen (CiA 301) at 250 kbit/s**. `COB-ID = (function code << 7) | node id`.
Per-object panel sweep: `panel_od_map.md`.

## Nodes

| Node | ID | Role | Status |
|------|----|------|--------|
| Panel | 11 (`0x0B`) | control panel | confirmed |
| Board | 21 (`0x15`) | relay switchboard | confirmed |
| — | 4 (`0x04`) | sensor/status (`204` = rolling counter) | observed, not investigated |

## COB-IDs in use

| COB-ID | Function | Produced by | Consumed by | Meaning | Confirmed |
|--------|----------|-------------|-------------|---------|-----------|
| `18B` | TPDO1 (panel) / RPDO1 (board) | Panel `0x4000` | Board → `0x4001` | **relay-state command** bitmap (4 B) | ✅ |
| `20B` | TPDO1 (board) / RPDO1 (panel) | Board `0x4000` | Panel → `0x4001` | **relay-state confirm/echo** (4 B) | ✅ |
| `08B` / `095` | EMCY | panel / board | all | error + bus-state codes | ✅ |
| `70B` / `715` | NMT boot-up | panel / board | all | one-shot `00` at boot — **no periodic heartbeat** (`1017` = 0) | ✅ |
| `58B` / `595` | SDO server (tx) | panel / board | SDO client | SDO responses | ✅ |
| `60B` / `615` | SDO client (rx) | client (Pi) | panel / board | SDO requests | ✅ |
| `48B` / `495` | boot id/version | panel / board | — | device id announced at boot | ✅ |
| `000` | NMT | Pi only (during investigation) | all | node control (reset/start) | none captured from panel/board |

## Relay-state frame (`18B` / `20B`) — 4 bytes

| Byte | Bits | Meaning | Confirmed |
|------|------|---------|-----------|
| 0 | bit 0 | **alive toggle** — *must alternate* each frame or the board ignores the command (not to be confused with CANopen NMT heartbeat, which is off — `1017` = 0) | ✅ |
| 0 | bits 1–7 | relay bitmap (low 7 bits) | ✅ |
| 1 | all | relay bitmap (mid 8 bits) | ✅ |
| 2 | all | relay bitmap (high 8 bits) | ✅ |
| 3 | all | unused — always `00` | ✅ |

24-bit bitmap; bit 0 is the toggle, so **23 usable circuit bits**. Byte 3 is dead space.

### Relay map
    ALIVE_TOGGLE    = 0x00000001
    ANCHOR          = 0x00000002
    BILGE_PUMP      = 0x00000004
    LANTERN_BOW     = 0x00000008
    CABIN_LIGHTS2   = 0x00000010
    CABIN_LIGHTS1   = 0x00000020
    COMPASS_LIGHT   = 0x00000040
    DECK_LIGHT      = 0x00000080
    HEATER          = 0x00000100
    LATERN_MASTHEAD = 0x00000200
    INSTRUMENTS     = 0x00000400
    MUSIC           = 0x00000800
    FRIDGE          = 0x00001000
    SHOWER          = 0x00002000
    LANTERN_STEAM   = 0x00004000
    LANTERN_AFT     = 0x00008000
    F1         	    = 0x00010000
    F2              = 0x00020000
    F3              = 0x00040000
    F4              = 0x00080000
    F5              = 0x00100000
    WATER           = 0x00200000
    RESERVED1       = 0x00400000
    RESERVED2       = 0x00800000

## PDO configuration (SDO-confirmed, both nodes)

Both nodes are the **same OD/firmware stack** (`CODEVICE`, `Version 4.5`), configured as
mirror images. **Identical mapping** on both — the difference is firmware role (below).

| Object | Panel (n11) | Board (n21) | Meaning |
|--------|-------------|-------------|---------|
| `1400:1` RPDO COB-ID | `0x20B` | `0x18B` | id the node **receives** on |
| `1600:1` RPDO mapping | `0x4001` (32-bit) | `0x4001` (32-bit) | received data → `0x4001` |
| `1800:1` TPDO COB-ID | `0x18B` | `0x20B` | id the node **transmits** on |
| `1A00:1` TPDO mapping | `0x4000` (32-bit) | `0x4000` (32-bit) | transmitted data ← `0x4000` |

## State objects

| Object | Panel access | Board access | Role |
|--------|--------------|--------------|------|
| `0x4000` | **RO** | readable | outgoing/broadcast state (→ TPDO). Panel: owned by physical buttons. |
| `0x4001` | **WO**, ignored for state | readable | incoming state (← RPDO). **Board adopts** it → `0x4000` + relays. **Panel does not.** |

## Writability (confirmed by same-value SDO writes)

| Object | Panel | Board | Note |
|--------|-------|-------|------|
| `1400:1` RPDO COB-ID | writable | **writable** ✅ — same-value write live; *changing* the id needs the invalid-bit disable dance | the repoint lever |
| `1400:2` RPDO txtype | writable | — | `0xFF` async |
| `1800:1` TPDO COB-ID | writable | rejects in-place (`0x06090030`) | needs disable-dance |
| `1600` / `1A00` mapping | **locked RO** | (assumed locked) | cannot remap |
| `0x4000` state | **RO** | — | firmware-owned |
| `0x4001` incoming | **WO**, ignored | — | never folds into `0x4000` |
| `0x2200`–`0x2822` mfr | **RO** | — | no writable command object |

## Key behavioural findings

- **Board obeys `18B` and drives relays** — confirmed. It only accepts a command whose
  **byte-0 alive-toggle bit alternates**; a static frame is treated as a dead source and ignored.
- **Panel is a state _source only_** — confirmed. Its `0x4000` is RO and its `0x4001` inbox is
  never folded into state. A real, toggling `20B` carrying a *mismatched* state is **silently
  ignored** (no adopt, no EMCY). Only physical buttons change panel state. No bus path, flag
  bit, or SDO can command the panel.
- **Board vs panel = same firmware, opposite role:** the board copies its RPDO inbox
  (`0x4001`) into its state (`0x4000` + relays); the panel does not. This role — not the
  mapping — is why the board follows and the panel leads.
- **Command interruption drops relays** — with the board's RPDO disabled for
  ~150 ms mid-repoint, the board switched **all relays off** until commands
  resumed (observed 2026-07-19); a <10 ms disabled window causes no glitch.
  Exact supervision timeout unmeasured — keep any RPDO reconfiguration
  window minimal, with no delays between the SDO writes.
- **The repoint approach** — the board's RPDO can be repointed from `0x18B`
  to a Pi COB-ID **live over SDO** (disable → set → enable). The board then
  obeys the Pi and ignores the panel's `0x18B`. The change is **volatile**
  (a power cycle reverts it to `0x18B`). This finding is the basis of the
  takeover mechanism designed in `architecture.md`.

## Startup sequence (capture: `startup2`, both nodes on one bus)

Boot order per node: boot-id frame (`495`/`48B`) → NMT boot-up (`715`/`70B`,
one-shot `00`) → EMCY burst (`0x8120` CAN-error-passive noise while a node is
alone on the bus; benign) → TPDO stream starts immediately at state `0`,
toggle bit alternating every frame.

- **Panel remembers its relay state** across a power cycle: it first streams
  `18B` with bitmap `0`, then re-asserts the remembered bitmap a few frames
  later.
- **Board adopts from the stream**: it echoes `0` on `20B` until the panel's
  remembered state arrives, then follows it — confirms the adopt-from-RPDO
  role.
- Both TPDOs stream periodically from boot even with empty state, so
  `18B`/`20B` presence is a reliable liveness signal; `495`/`48B` and
  `715`/`70B` are reliable one-shot reboot markers.
