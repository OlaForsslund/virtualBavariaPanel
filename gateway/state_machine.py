"""Pure-logic gateway state machine (architecture.md §6).

No I/O, no threads, no wall clock: the driver feeds bus observations and
commands with an explicit monotonic timestamp and executes the actions
returned (SDO repoint / release, reporting results back). Streaming on
0x18C is implied by state: the driver streams `output_bitmap` whenever
`streaming` is true.

Notes:
- deactivate() during ACTIVATING is ignored (the repoint SDO sequence is
  ~200 ms; callers retry once it lands in ACTIVE).
- Panel edges are applied per circuit, last write wins (§5); a panel
  frame that merely restates unchanged panel state never overrides web
  commands (edge-triggered).
"""

from enum import Enum, auto


class State(Enum):
    PASSIVE = auto()
    WAITING_FOR_BOARD = auto()
    ACTIVATING = auto()
    ACTIVE = auto()
    DEACTIVATING = auto()


class Action(Enum):
    REPOINT = auto()  # run disable/set/enable to 0x18C, then report result
    RELEASE = auto()  # write 1400:1 back to 0x18B, then call release_done()


class GatewayStateMachine:
    # Board streams every ~25 ms; thresholds calibrated on hardware 2026-07-19.
    BOARD_SILENCE_TIMEOUT = 1.0
    ECHO_MISMATCH_TIMEOUT = 0.5
    REPOINT_RETRY_DELAY = 1.0

    def __init__(self) -> None:
        self.state = State.PASSIVE
        self.output_bitmap = 0
        self.panel_bitmap: int | None = None
        self.board_bitmap: int | None = None
        self._last_board_time: float | None = None
        self._last_echo_ok: float = 0.0
        self._retry_after: float = 0.0

    @property
    def streaming(self) -> bool:
        return self.state in (State.ACTIVATING, State.ACTIVE)

    # -- commands ---------------------------------------------------------

    def activate(self, now: float) -> list[Action]:
        if self.state is not State.PASSIVE:
            return []
        self.state = State.WAITING_FOR_BOARD
        return self._try_repoint(now)

    def deactivate(self, now: float) -> list[Action]:
        if self.state not in (State.ACTIVE, State.WAITING_FOR_BOARD):
            return []
        self.state = State.DEACTIVATING
        return [Action.RELEASE]

    def set_circuit(self, mask: int, on: bool) -> bool:
        """Web-originated command. Only accepted while ACTIVE."""
        if self.state is not State.ACTIVE:
            return False
        if on:
            self.output_bitmap |= mask
        else:
            self.output_bitmap &= ~mask
        return True

    # -- driver results ---------------------------------------------------

    def repoint_succeeded(self, now: float) -> None:
        if self.state is not State.ACTIVATING:
            return
        self.state = State.ACTIVE
        self._last_echo_ok = now

    def repoint_failed(self, now: float) -> None:
        if self.state is State.ACTIVATING:
            self.state = State.WAITING_FOR_BOARD
            self._retry_after = now + self.REPOINT_RETRY_DELAY

    def release_done(self, now: float) -> None:
        if self.state is State.DEACTIVATING:
            self.state = State.PASSIVE

    # -- bus observations -------------------------------------------------

    def on_panel_frame(self, bitmap: int, now: float) -> list[Action]:
        previous = self.panel_bitmap
        self.panel_bitmap = bitmap
        if self.state is State.ACTIVE and previous is not None and previous != bitmap:
            changed = previous ^ bitmap
            self.output_bitmap = (self.output_bitmap & ~changed) | (bitmap & changed)
        return []

    def on_board_frame(self, bitmap: int, now: float) -> list[Action]:
        self.board_bitmap = bitmap
        self._last_board_time = now
        if self.state is State.ACTIVE and bitmap == self.output_bitmap:
            self._last_echo_ok = now
        return self._try_repoint(now)

    def on_board_boot(self, now: float) -> list[Action]:
        """0x495 or 0x715 seen: the board rebooted, any repoint is gone."""
        if self.state in (State.ACTIVE, State.ACTIVATING):
            self.state = State.WAITING_FOR_BOARD
        self._last_board_time = None  # wait for 0x20B before repointing
        return []

    def tick(self, now: float) -> list[Action]:
        """Call periodically (e.g. every stream period) for timeout checks."""
        if self.state is State.ACTIVE:
            silent = (
                self._last_board_time is None
                or now - self._last_board_time > self.BOARD_SILENCE_TIMEOUT
            )
            mismatch = now - self._last_echo_ok > self.ECHO_MISMATCH_TIMEOUT
            if silent or mismatch:
                self.state = State.WAITING_FOR_BOARD
        return self._try_repoint(now)

    # -- internal ---------------------------------------------------------

    def _try_repoint(self, now: float) -> list[Action]:
        board_fresh = (
            self._last_board_time is not None
            and now - self._last_board_time <= self.BOARD_SILENCE_TIMEOUT
        )
        if self.state is State.WAITING_FOR_BOARD and board_fresh and now >= self._retry_after:
            self.state = State.ACTIVATING
            # Adopt current state NOW: the 0x18C stream starts during
            # ACTIVATING and must already carry the right bitmap the
            # moment the board's RPDO enables on it (else relays blip).
            adopted = self.board_bitmap if self.board_bitmap is not None else self.panel_bitmap
            self.output_bitmap = adopted or 0
            return [Action.REPOINT]
        return []
