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
| `2200`, `2204` | 20× 16-bit ~`0x00E9` | analog inputs (two banks; most channels are jitter on capacitive touch, but subs 15/17 are real — see below) |
| `2304`, `2404`, `2405`, `2602` | 27× bytes, mostly `00` | per-channel digital state / config |
| `2600` / `2601` | 32-bit | clean relay bitmap (mirrors of state) |
| `2500`–`2503`, `2700`–`2708`, `2800`–`2822` | mixed | config / timers (`2501:9 = 0x8B` = own node-id byte) |

### Analog sensor readings (confirmed 2026-07-25)

Correlated live against the panel's own display and a physical test, gateway stopped
throughout (board back on the panel's `18B`, no interference):

| Obj:sub | Reading | Evidence |
|---------|---------|----------|
| `2200:15` / `2204:15` (mirrored) | **starter battery voltage** — raw counts, `volts ≈ raw × 0.01495` (≈66.9 counts/volt) | started at `910`; when the starter battery was switched off, decayed smoothly `910 → 0` over ~68s (capacitor bleed-down, not a step) while `sub17` stayed rock-steady — isolates it unambiguously from the other voltage channel. Reconnected afterwards: back to `13.61V`, consistent. |
| `2200:17` / `2204:17` (mirrored) | **house battery voltage** — same scale | held at `909` (≈13.6V) throughout the starter-off test, unaffected |
| `2501:1` | **freshwater tank level**, plain byte `0`–`100` | read `25` (`0x19`), matched panel display "25%" exactly |
| `2501:4` | **blackwater tank level**, plain byte `0`–`100` | read `75` (`0x4B`), matched panel display "75%"; later read `0` (confirmed correct — tank was actually empty by then). **This sender is known to misfire** — treat single readings with caution, don't assume a changed value means a real level change without corroboration. |

**Voltage calibration note:** the panel's own display reads ~0.2–0.24V *high* — it
showed `13.8V` for a raw count of `909`/`910`, while an independent Victron and a
voltmeter both agreed on `13.56V`/`13.61V` for the same raw count. The
`0.01495 V/count` scale above is calibrated against the trusted external readings,
not the panel's display. Still only a single-point calibration (assumes a
zero-offset linear scale) — a second reading at a meaningfully different voltage,
cross-checked against an external meter, would confirm there's no fixed offset too.
Constant: `gateway/constants.py` `BATTERY_VOLTS_PER_COUNT`.

These four values are now exposed at runtime via `GET /sensors` (`gateway/web.py`),
polled every 5s from the panel node directly — independent of the takeover/repoint
mechanism, works in any gateway state.

Likely **not** true continuous percentages — the tank senders are probably discrete
float switches (freshwater: at least `25`/`50`/`75`/`100` steps; blackwater: possibly
only a single high-level switch at `75`, i.e. just `0` or `75`). Only one reading per
tank has actually been observed (`25` fresh, `75` black); the other steps are inferred
from the sender design, not confirmed on the bus. `2501:2/3/5/6/7` all read `0` —
likely spare tank slots (greywater/fuel) not fitted on this boat.

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
