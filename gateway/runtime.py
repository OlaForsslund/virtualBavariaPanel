"""Gateway runtime: wires the pure state machine to the real bus.

Threads: the main receive loop (bus frames -> state machine -> SDO
actions), the Streamer (transmits on 0x18C every stream period while
there is a frame to send), and the REST server (gateway/web.py). The
state machine is single-threaded — only the main loop touches it.
Cross-thread hand-off is lock-free, no locks, two directions:
- out: the main loop calls _publish_buffers() after every state-machine
  interaction, writing an immutable snapshot to StreamBuffer (polled by
  the Streamer) and StatusBuffer (polled by REST reads).
- in: CommandQueue.submit() from the REST thread queues a command;
  the main loop drains it once per iteration. The web layer must never
  call the state machine directly.
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import can
import canopen
import uvicorn

from gateway import constants
from gateway.command_queue import CommandQueue
from gateway.config import Config
from gateway.frames import decode_state, encode_state
from gateway.monitor import BusMonitor
from gateway.state_machine import PASSIVE, DEACTIVATING, Action, GatewayStateMachine
from gateway.storage import Storage
from gateway.web import create_app

log = logging.getLogger("gateway")

INVALID_BIT = 0x80000000
TICK_PERIOD = 0.1
SENSOR_POLL_PERIOD = 5.0


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


class WebServer(threading.Thread):
    """Runs the REST app (gateway/web.py) via uvicorn. Its own thread.

    uvicorn's signal handling auto-detects non-main threads and skips
    itself (uvicorn>=0.51), so no extra setup is needed to run it here.
    """

    daemon = True

    def __init__(self, app, host: str, port: int) -> None:
        super().__init__(name="web")
        self._server = uvicorn.Server(
            uvicorn.Config(app, host=host, port=port, log_level="warning")
        )

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True


@dataclass(frozen=True)
class StatusSnapshot:
    state: str
    output_bitmap: int
    panel_bitmap: int | None
    board_bitmap: int | None
    streaming: bool


class StatusBuffer:
    """Lock-free single-writer/multi-reader hand-off for REST status reads.

    Same rationale as StreamBuffer: a plain attribute assignment of an
    immutable snapshot is atomic in CPython, so the main loop (writer) and
    any number of REST handler threads (readers) need no lock.
    """

    def __init__(self) -> None:
        self.snapshot: StatusSnapshot | None = None


@dataclass(frozen=True)
class SensorSnapshot:
    starter_voltage: float
    house_voltage: float
    freshwater_pct: int
    blackwater_pct: int
    read_at: float  # time.monotonic() of the read, so staleness is visible to callers


class SensorBuffer:
    """Same lock-free single-writer/multi-reader hand-off as StatusBuffer,
    for the panel's analog sensors (battery voltages, tank levels). Polled
    on its own cadence (SENSOR_POLL_PERIOD), independent of state-machine
    ticks — reading these is plain SDO traffic to the panel node, unrelated
    to the takeover/repoint mechanism.
    """

    def __init__(self) -> None:
        self.snapshot: SensorSnapshot | None = None


class GatewayRuntime:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.sm = GatewayStateMachine()
        self.monitor = BusMonitor()
        self.stream_buffer = StreamBuffer()
        self.status_buffer = StatusBuffer()
        self.sensor_buffer = SensorBuffer()
        self.command_queue = CommandQueue()
        self.storage = Storage(Path(cfg.data_dir))
        self._logged_state = self.sm.state
        self._shutdown = threading.Event()
        self._publish_buffers()  # so GET /status has something before the first frame/tick

        self.bus = can.Bus(interface=cfg.can_interface, channel=cfg.can_channel)
        self.network = canopen.Network()
        self.network.connect(interface=cfg.can_interface, channel=cfg.can_channel)
        self.node = self.network.add_node(constants.BOARD_NODE_ID)
        self.panel_node = self.network.add_node(constants.PANEL_NODE_ID)
        self.streamer = Streamer(self.bus, cfg.stream_period, self.stream_buffer)
        self.web_server = WebServer(create_app(self), cfg.web_host, cfg.web_port)

    # -- commands (main thread only) --------------------------------------

    def activate(self) -> None:
        self._execute(self.sm.activate(time.monotonic()))

    def deactivate(self) -> None:
        self._execute(self.sm.deactivate(time.monotonic()))

    def cmd_set_circuit(self, mask: int, on: bool) -> None:
        """Web-originated circuit command. Reaches the queue via CommandQueue only."""
        self.sm.set_circuit(mask, on)
        self._publish_buffers()

    # -- main loop --------------------------------------------------------

    def run(self) -> None:
        self.streamer.start()
        self.web_server.start()
        last_tick = 0.0
        last_sensor_poll = 0.0
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
            self.command_queue.drain()
            if now - last_sensor_poll >= SENSOR_POLL_PERIOD:
                self._poll_sensors()
                last_sensor_poll = now

    def request_shutdown(self) -> None:
        """Thread-safe: signal handlers may call this from outside the main loop."""
        self._shutdown.set()

    def shutdown(self) -> None:
        self._shutdown.set()
        self.deactivate()
        if self.sm.state not in (PASSIVE, DEACTIVATING):
            # e.g. interrupted mid-ACTIVATING: hand back regardless.
            log.warning("shutdown in state %s — best-effort release", self.sm.state.name)
            self._release()
        self.streamer.stop()
        self.streamer.join(timeout=1.0)
        self.web_server.stop()
        self.web_server.join(timeout=1.0)
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
        self._publish_buffers()
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
            self._publish_buffers()

    def _publish_buffers(self) -> None:
        """Snapshot the state machine for the Streamer and REST reads (atomic)."""
        self.stream_buffer.bitmap = self.sm.output_bitmap if self.sm.streaming else None
        self.status_buffer.snapshot = StatusSnapshot(
            state=self.sm.state.name,
            output_bitmap=self.sm.output_bitmap,
            panel_bitmap=self.sm.panel_bitmap,
            board_bitmap=self.sm.board_bitmap,
            streaming=self.sm.streaming,
        )
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

    def _poll_sensors(self) -> None:
        try:
            starter_raw = int.from_bytes(
                self.panel_node.sdo.upload(constants.BATTERY_STARTER_INDEX, constants.BATTERY_STARTER_SUB)[:2],
                "little",
            )
            house_raw = int.from_bytes(
                self.panel_node.sdo.upload(constants.BATTERY_HOUSE_INDEX, constants.BATTERY_HOUSE_SUB)[:2],
                "little",
            )
            fresh_pct = self.panel_node.sdo.upload(constants.TANK_FRESHWATER_INDEX, constants.TANK_FRESHWATER_SUB)[0]
            black_pct = self.panel_node.sdo.upload(constants.TANK_BLACKWATER_INDEX, constants.TANK_BLACKWATER_SUB)[0]
        except (canopen.SdoAbortedError, canopen.SdoCommunicationError) as exc:
            log.warning("sensor poll failed: %s", exc)
            return
        self.sensor_buffer.snapshot = SensorSnapshot(
            starter_voltage=round(starter_raw * constants.BATTERY_VOLTS_PER_COUNT, 2),
            house_voltage=round(house_raw * constants.BATTERY_VOLTS_PER_COUNT, 2),
            freshwater_pct=fresh_pct,
            blackwater_pct=black_pct,
            read_at=time.monotonic(),
        )

    def _log_state(self) -> None:
        state = self.sm.state
        if state is not self._logged_state:
            log.info("state: %s -> %s", self._logged_state.name, state.name)
            self._logged_state = state
