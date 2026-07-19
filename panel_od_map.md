# Panel Object Dictionary — node 11 (`0x0B`)

Read-only SDO sweep of the control panel (92 objects), produced with the `wardialer`
tooling (`sdo_read.py --scan`) kept in the separate protocol-analysis repo, which also
holds the raw captures (`od_scan_panel.{log,summary,clean}`, `before/after.snap`).
Companion: **`protocol_findings.md`** (bus protocol and PDO findings); the resulting
design lives in `architecture.md`.

Generic CANopen stack: `1008 = CODEVICE`, `1009 = platform`, `100A = Version 4.5`.
**Access legend:** ✅ = write-tested/confirmed; otherwise read-only observed (writability
untested unless in the writability table).

## Communication profile (`0x1000`s)

| Obj | Value | Meaning | Confirmed |
|-----|-------|---------|-----------|
| `1000` | `0` | device type | ✅ |
| `1001` | `0x11` | error register | ✅ |
| `1003` | 1 entry | predefined error field | ✅ |
| `1005` | `0x80` | SYNC COB-ID | ✅ |
| `1006`/`1007` | `0` | sync cycle / window (no SYNC produced) | ✅ |
| `1008`/`1009`/`100A` | strings | id / platform / version | ✅ |
| `1014` | `0x8B` | EMCY COB-ID (= node 11) | ✅ |
| `1017` | `0` | producer heartbeat (off) | ✅ |
| `1018` | all `0` | identity (unset) | ✅ |
| `1400` / `1600` | `0x20B` / → `0x4001` | **RPDO1** comm + mapping (the one input) | ✅ |
| `1800` / `1A00` | `0x18B` / ← `0x4000` | **TPDO1** comm + mapping (the one output) | ✅ |
| `1F80` | `0x08` | NMT startup (auto-operational) | ✅ |

## State objects (`0x4000`s)

| Obj | Access | Meaning |
|-----|--------|---------|
| `4000` | **RO** | outgoing relay state, broadcast on `18B`. Owned by physical buttons. Write → abort `0x06010002`. |
| `4001` | **WO** | incoming state, written by the board's `20B` RPDO — but **never folded into `0x4000`**, so the panel does not adopt it. |

## Manufacturer area (`0x2200`s) — I/O and config (read-only)

| Obj | Shape | Guess |
|-----|-------|-------|
| `2200`, `2204` | 20× 16-bit ~`0x00E9` | analog inputs (two banks; jitter on capacitive touch) |
| `2304`, `2404`, `2405`, `2602` | 27× bytes, mostly `00` | per-channel digital state / config |
| `2600` / `2601` | 32-bit | clean relay bitmap (mirrors of state) |
| `2500`–`2503`, `2700`–`2708`, `2800`–`2822` | mixed | config / timers (`2501:9 = 0x8B` = own node-id byte) |

## Device-info block (`0x5F00`s)

| Obj | Value | Meaning |
|-----|-------|---------|
| `5FF5` | `0x0B` | node id (11) |
| `5FF0` / `5FF1` | `06/24/15` / `08/25/16` | date strings |
| `5FE0` | `KokO` | tag/marker |
| `5FF6` | `3F 02 D9 BC` | matches the `48B` (boot id) version tail |

## Button-press correlation (physical `CAB1` / `0x20` light ON)

Diff of `before.snap` → `after.snap` (analysis repo) across one press:

| Obj:sub | before → after | meaning |
|---------|----------------|---------|
| `4000:0` | `00…` → `21 00 00 00` | broadcast state = bitmap `0x20` + toggle |
| `2600:0` | `00…` → `20 00 00 00` | clean relay bitmap |
| `2601:0` | `00…` → `20 00 00 00` | clean relay bitmap (copy) |
| `2304:3` | `00` → `01` | per-channel flag → **CAB1 = channel index 3** |
| `2305:0` | `00` → `01` | aggregate change flag |

## Writability — tested (SDO writes)

| Obj:sub | Content | Result |
|---------|---------|--------|
| `1400:1` | RPDO COB-ID | **writable** (can redirect which COB-ID it listens on) |
| `1400:2` | RPDO txtype | writable |
| `1800:1/2/5` | TPDO COB-ID / txtype / inhibit | writable |
| `1005`,`1006`,`1007`,`100C`,`100D`,`1015`,`1017` | standard comms | writable |
| `1600` / `1A00` | PDO mapping | **locked (RO)** |
| `4000:0` | relay state | **RO** — abort `0x06010002` |
| `4001:0` | incoming state | writable but **ignored for state** (panel does not adopt) |
| `2600:0`,`2601:0`,`2304:3`,`2305:0` | state mirrors | **RO** — abort `0x06010002` |
| `2200`–`2822` | all manufacturer objects | **RO** |

## Takeaways

- Panel has exactly **one PDO input** (`20B → 0x4001`, ignored) and **one PDO output**
  (`0x4000 → 18B`, RO). No writable object changes the panel's relay memory — **only
  physical buttons do**. The panel cannot be commanded over the bus.
- Only comms/PDO *comm-parameter* objects are writable; PDO **mapping is locked** and no
  manufacturer "command/mode" object exists.
- Consequence: a second panel cannot make this panel agree; control must move board-side
  (the repoint approach — finding in `protocol_findings.md`, design in `architecture.md`).
