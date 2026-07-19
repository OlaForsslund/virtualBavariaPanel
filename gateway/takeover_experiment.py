"""Supervised first takeover experiment.

Proves the ACTIVATING/ACTIVE/DEACTIVATING mechanics (architecture.md §6)
as a linear script before folding them into the state machine. Every
phase prints what it does. The release write runs in a finally block, so
any failure still attempts to hand control back to the panel; residual
risk is covered by the volatile repoint (power-cycling the board always
restores panel control).

Keep hands off the panel while it runs.
"""

import statistics
import threading
import time

import can
import canopen

from gateway import constants
from gateway.config import load_config
from gateway.frames import decode_state, encode_state, relay_names

SAFE_RELAY = "DECK_LIGHT"
SAFE_MASK = constants.RELAYS[SAFE_RELAY]
INVALID_BIT = 0x80000000
COB_PANEL = constants.COB_PANEL_STATE
COB_BOARD = constants.COB_BOARD_CONFIRM
COB_GATEWAY = constants.COB_GATEWAY_STATE

T0 = time.monotonic()


def step(text: str) -> None:
    print(f"[{time.monotonic() - T0:6.2f}s] {text}", flush=True)


class Tracker(can.Listener):
    """Keeps the latest decoded state frame and recent timestamps per COB-ID."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[int, int] = {}
        self._stamps: dict[int, list[float]] = {COB_PANEL: [], COB_BOARD: []}

    def on_message_received(self, msg: can.Message) -> None:
        if msg.is_error_frame or msg.dlc != 4:
            return
        if msg.arbitration_id in (COB_PANEL, COB_BOARD):
            frame = decode_state(bytes(msg.data))
            with self._lock:
                self._latest[msg.arbitration_id] = frame.bitmap
                stamps = self._stamps[msg.arbitration_id]
                stamps.append(msg.timestamp)
                del stamps[:-32]

    def bitmap(self, cob_id: int) -> int | None:
        with self._lock:
            return self._latest.get(cob_id)

    def frame_count(self, cob_id: int) -> int:
        with self._lock:
            return len(self._stamps[cob_id])

    def period(self, cob_id: int) -> float:
        with self._lock:
            stamps = list(self._stamps[cob_id])
        return statistics.median(b - a for a, b in zip(stamps, stamps[1:]))

    def wait(self, predicate, timeout: float, what: str) -> float:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if predicate():
                return time.monotonic() - start
            time.sleep(0.01)
        raise TimeoutError(f"timeout after {timeout}s waiting for: {what}")


class Streamer(threading.Thread):
    """Streams the gateway state on 0x18C with alternating alive toggle."""

    daemon = True

    def __init__(self, bus: can.BusABC, period: float, bitmap: int) -> None:
        super().__init__()
        self.bus = bus
        self.period = period
        self.bitmap = bitmap
        self._stop_evt = threading.Event()  # NB: Thread itself owns "_stop"

    def run(self) -> None:
        toggle = False
        while True:
            msg = can.Message(
                arbitration_id=COB_GATEWAY,
                data=encode_state(self.bitmap, toggle),
                is_extended_id=False,
            )
            self.bus.send(msg)
            toggle = not toggle
            if self._stop_evt.wait(self.period):
                return

    def stop(self) -> None:
        self._stop_evt.set()


def write_rpdo_cob(node: canopen.RemoteNode, value: int) -> None:
    # No delay between writes: an RPDO-disabled window of ~150 ms drops
    # all relays (protocol_findings.md).
    node.sdo.download(
        constants.RPDO1_COB_ID_INDEX,
        constants.RPDO1_COB_ID_SUB,
        value.to_bytes(4, "little"),
    )


def repoint(node: canopen.RemoteNode, old: int, new: int) -> None:
    write_rpdo_cob(node, INVALID_BIT | old)
    write_rpdo_cob(node, INVALID_BIT | new)
    write_rpdo_cob(node, new)


def main() -> None:
    cfg = load_config()
    bus = can.Bus(interface=cfg.can_interface, channel=cfg.can_channel)
    tracker = Tracker()
    notifier = can.Notifier(bus, [tracker])
    network = canopen.Network()
    network.connect(interface=cfg.can_interface, channel=cfg.can_channel)
    node = network.add_node(constants.BOARD_NODE_ID)
    streamer = None
    try:
        step("1. observing bus, measuring panel cadence")
        tracker.wait(lambda: tracker.frame_count(COB_PANEL) >= 10, 30, "10 panel frames")
        tracker.wait(lambda: tracker.frame_count(COB_BOARD) >= 2, 5, "board frames")
        period = tracker.period(COB_PANEL)
        if not 0.02 <= period <= 2.0:
            raise RuntimeError(f"implausible panel period {period:.3f}s — aborting")
        panel = tracker.bitmap(COB_PANEL)
        board = tracker.bitmap(COB_BOARD)
        step(f"   panel period {period * 1000:.0f} ms, state: {', '.join(relay_names(panel)) or 'all off'}")
        if panel != board:
            raise RuntimeError(f"echo mismatch before start: panel={panel:06X} board={board:06X}")
        if panel & SAFE_MASK:
            raise RuntimeError(f"{SAFE_RELAY} is currently ON — aborting, need it OFF for the test")

        step("2. reading baseline 1400:1")
        baseline = int.from_bytes(
            node.sdo.upload(constants.RPDO1_COB_ID_INDEX, constants.RPDO1_COB_ID_SUB), "little"
        )
        if baseline != COB_PANEL:
            raise RuntimeError(f"unexpected 1400:1 = 0x{baseline:08X}, want 0x{COB_PANEL:08X}")

        step("3. streaming current state on 0x18C (board still ignores it)")
        streamer = Streamer(bus, period, panel)
        streamer.start()
        time.sleep(1.0)

        try:
            step("4. repointing 1400:1 -> 0x18C (disable/set/enable)")
            repoint(node, COB_PANEL, COB_GATEWAY)

            step("5. verifying board keeps echoing our (unchanged) state")
            time.sleep(1.0)
            if tracker.bitmap(COB_BOARD) != streamer.bitmap:
                raise RuntimeError("board echo diverged right after repoint")

            step(f"6. commanding {SAFE_RELAY} ON from the gateway")
            streamer.bitmap |= SAFE_MASK
            latency = tracker.wait(
                lambda: tracker.bitmap(COB_BOARD) & SAFE_MASK, 2.0, f"{SAFE_RELAY} ON in echo"
            )
            step(f"   board confirmed ON after {latency * 1000:.0f} ms — control is ours")
            time.sleep(2.0)
            step(f"   commanding {SAFE_RELAY} OFF")
            streamer.bitmap &= ~SAFE_MASK
            latency = tracker.wait(
                lambda: not tracker.bitmap(COB_BOARD) & SAFE_MASK, 2.0, f"{SAFE_RELAY} OFF in echo"
            )
            step(f"   board confirmed OFF after {latency * 1000:.0f} ms")
        finally:
            step("7. releasing: 1400:1 -> 0x18B, stopping stream")
            repoint(node, COB_GATEWAY, COB_PANEL)
            if streamer:
                streamer.stop()

        step("8. verifying board follows the panel again")
        tracker.wait(
            lambda: tracker.bitmap(COB_BOARD) == tracker.bitmap(COB_PANEL),
            3.0,
            "board echo to match panel",
        )
        readback = int.from_bytes(
            node.sdo.upload(constants.RPDO1_COB_ID_INDEX, constants.RPDO1_COB_ID_SUB), "little"
        )
        step(f"   1400:1 = 0x{readback:08X}, echo matches panel")
        step("PASS — takeover and release verified. Press a panel button to double-check.")
    finally:
        if streamer:
            streamer.stop()
        notifier.stop()
        network.disconnect()
        bus.shutdown()


if __name__ == "__main__":
    main()
