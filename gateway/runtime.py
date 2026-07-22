"""Gateway runtime: wires the pure state machine to the real bus.

Threads: the main receive loop (bus frames -> state machine -> SDO
actions) and the Streamer (transmits on 0x18C every stream period while
there is a frame to send). The state machine is single-threaded — only
the main loop touches it. The sole cross-thread hand-off is StreamBuffer:
the main loop publishes an immutable snapshot after every state-machine
interaction, the Streamer polls it. No locks; a future web interface must
marshal commands into the main loop (queue), never call the state machine
from its own thread.
"""

import logging
import threading
import time

import can
import canopen

from gateway import constants
from gateway.config import Config
from gateway.frames import decode_state, encode_state
from gateway.monitor import BusMonitor
from gateway.state_machine import PASSIVE, DEACTIVATING, Action, GatewayStateMachine

log = logging.getLogger("gateway")

INVALID_BIT = 0x80000000
TICK_PERIOD = 0.1


class StreamBuffer:
    """Lock-free single-writer/single-reader hand-off to the Streamer.

    `bitmap` is the circuit bitmap to stream, or None to stream nothing.
    A plain attribute assignment of an immutable value is atomic in
    CPython, so writer (main loop) and reader (Streamer) need no lock.
    """

    def __init__(self) -> None:
        self.bitmap: int | None = None


class Streamer(threading.Thread):
    daemon = True

    def __init__(self, bus: can.BusABC, period: float, buffer: StreamBuffer) -> None:
        super().__init__(name="streamer")
        self.bus = bus
        self.period = period
        self.buffer = buffer
        self._stop_evt = threading.Event()  # NB: Thread itself owns "_stop"

    def run(self) -> None:
        toggle = False
        while not self._stop_evt.wait(self.period):
            bitmap = self.buffer.bitmap
            if bitmap is not None:
                msg = can.Message(
                    arbitration_id=constants.COB_GATEWAY_STATE,
                    data=encode_state(bitmap, toggle),
                    is_extended_id=False,
                )
                try:
                    self.bus.send(msg)
                except can.CanError as exc:
                    log.warning("stream send failed: %s", exc)
                    continue
                toggle = not toggle

    def stop(self) -> None:
        self._stop_evt.set()


class GatewayRuntime:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.sm = GatewayStateMachine()
        self.monitor = BusMonitor()
        self.stream_buffer = StreamBuffer()
        self._logged_state = self.sm.state
        self._shutdown = threading.Event()

        self.bus = can.Bus(interface=cfg.can_interface, channel=cfg.can_channel)
        self.network = canopen.Network()
        self.network.connect(interface=cfg.can_interface, channel=cfg.can_channel)
        self.node = self.network.add_node(constants.BOARD_NODE_ID)
        self.streamer = Streamer(self.bus, cfg.stream_period, self.stream_buffer)

    # -- commands (main thread only) --------------------------------------

    def activate(self) -> None:
        self._execute(self.sm.activate(time.monotonic()))

    def deactivate(self) -> None:
        self._execute(self.sm.deactivate(time.monotonic()))

    # -- main loop --------------------------------------------------------

    def run(self) -> None:
        self.streamer.start()
        last_tick = 0.0
        while not self._shutdown.is_set():
            msg = self.bus.recv(timeout=TICK_PERIOD)
            now = time.monotonic()
            actions = []
            if msg is not None and not msg.is_error_frame:
                for event in self.monitor.on_frame(msg.arbitration_id, bytes(msg.data)):
                    log.info(event)
                actions += self._dispatch(msg, now)
            if now - last_tick >= TICK_PERIOD:
                actions += self.sm.tick(now)
                last_tick = now
            self._execute(actions)

    def shutdown(self) -> None:
        self._shutdown.set()
        self.deactivate()
        if self.sm.state not in (PASSIVE, DEACTIVATING):
            # e.g. interrupted mid-ACTIVATING: hand back regardless.
            log.warning("shutdown in state %s — best-effort release", state.name)
            self._release()
        self.streamer.stop()
        self.streamer.join(timeout=1.0)
        self.network.disconnect()
        self.bus.shutdown()

    # -- internals --------------------------------------------------------

    def _dispatch(self, msg: can.Message, now: float) -> list[Action]:
        cob = msg.arbitration_id
        if cob == constants.COB_PANEL_STATE and msg.dlc == 4:
            return self.sm.on_panel_frame(decode_state(bytes(msg.data)).bitmap, now)
        if cob == constants.COB_BOARD_CONFIRM and msg.dlc == 4:
            return self.sm.on_board_frame(decode_state(bytes(msg.data)).bitmap, now)
        if cob in (constants.COB_BOARD_BOOTID, constants.COB_BOARD_BOOTUP):
            return self.sm.on_board_boot(now)
        return []

    def _execute(self, actions: list[Action]) -> None:
        self._publish_to_streamer()
        for action in actions:
            if action is Action.REPOINT:
                # Publish before the SDO sequence: the stream must already
                # carry the adopted state when the board's RPDO enables.
                ok = self._repoint(constants.COB_PANEL_STATE, constants.COB_GATEWAY_STATE)
                if ok:
                    self.sm.repoint_succeeded(time.monotonic())
                else:
                    self.sm.repoint_failed(time.monotonic())
            elif action is Action.RELEASE:
                self._release()
                self.sm.release_done(time.monotonic())
            self._publish_to_streamer()

    def _publish_to_streamer(self) -> None:
        """Snapshot the state machine's output for the Streamer (atomic)."""
        self.stream_buffer.bitmap = self.sm.output_bitmap if self.sm.streaming else None
        self._log_state()

    def _write_cob(self, value: int) -> None:
        self.node.sdo.download(
            constants.RPDO1_COB_ID_INDEX,
            constants.RPDO1_COB_ID_SUB,
            value.to_bytes(4, "little"),
        )

    def _repoint(self, old: int, new: int) -> bool:
        # The writes must run back-to-back — never add delays here: an
        # RPDO-disabled window of ~150 ms drops ALL relays until commands
        # resume; <10 ms is glitch-free (protocol_findings.md).
        log.info("repointing 1400:1 0x%03X -> 0x%03X", old, new)
        try:
            try:
                self._write_cob(new)  # in-place: no disabled window at all
            except canopen.SdoAbortedError:
                log.info("in-place write rejected, using disable dance")
                for value in (INVALID_BIT | old, INVALID_BIT | new, new):
                    self._write_cob(value)
            return True
        except (canopen.SdoAbortedError, canopen.SdoCommunicationError) as exc:
            log.error("repoint failed: %s", exc)
            return False

    def _release(self) -> None:
        if not self._repoint(constants.COB_GATEWAY_STATE, constants.COB_PANEL_STATE):
            log.error("release write failed — board reverts on its next power cycle")

    def _log_state(self) -> None:
        state = self.sm.state
        if state is not self._logged_state:
            log.info("state: %s -> %s", self._logged_state.name, state.name)
            self._logged_state = state
