"""Pure-logic gateway state machine (architecture.md §6).

No I/O, no threads, no wall clock: the driver feeds bus observations and
commands with an explicit monotonic timestamp and executes the actions
returned (SDO repoint / release, reporting results back). Streaming on
0x18C is implied by state: the driver streams `output_bitmap` whenever
`streaming` is true.

Structure: each state is a `State` singleton (constructed once at import
time - `transition_to()` never allocates, and the singletons double as
the identity you compare `GatewayStateMachine.state` against, e.g.
`sm.state is OPERATIONAL`). A state's full lifecycle lives in one class:
`enter()` is its setup phase, and its `on_*` overrides are every way it
can be left - read one class to see everything that can happen to that
state. `GatewayStateMachine.transition_to()` is the only place
`self._state` is assigned, and it always runs the entered state's
`enter()`.

`GatewayStateMachine`'s public methods (unchanged names - `runtime.py` and
the tests call these) do any bookkeeping that must happen regardless of
state (recording a bitmap, a timestamp) and then call the same-named method
on `self._state`. There is no `match self.state:` anywhere: which
state's code runs is decided by ordinary Python method dispatch on
whichever singleton `self._state` currently is - the polymorphism *is*
the switch. Deciding which of these methods to call in the first place
(from a CAN frame's COB-ID, or a REST command) is a separate, outer
concern that belongs to the driver (see `runtime.py`'s `_dispatch_can`),
not to this module.

Notes:
- deactivate() during ACTIVATING is ignored (the repoint SDO sequence is
  ~200 ms; callers retry once it lands in OPERATIONAL) - see the absence
  of an `on_deactivate` override on `ActivatingState`.
- Panel edges are applied per circuit, last write wins (§5); a panel
  frame that merely restates unchanged panel state never overrides web
  commands (edge-triggered) - see `OperationalState.on_panel_frame`.
"""

from enum import Enum, auto


class Action(Enum):
    REPOINT = auto()  # run disable/set/enable to 0x18C, then report result
    RELEASE = auto()  # write 1400:1 back to 0x18B, then call release_done()


class State:
    """Base class for a state: every hook defaults to "ignore, stay put"."""

    name: str
    streaming: bool = False

    def enter(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_activate(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_deactivate(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_board_frame(self, ctx: "GatewayStateMachine", bitmap: int, now: float) -> list[Action]:
        return []

    def on_panel_frame(
        self, ctx: "GatewayStateMachine", bitmap: int, previous: int | None, now: float
    ) -> list[Action]:
        return []

    def on_board_boot(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_tick(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_repoint_succeeded(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_repoint_failed(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def on_release_done(self, ctx: "GatewayStateMachine", now: float) -> list[Action]:
        return []

    def set_circuit(self, ctx: "GatewayStateMachine", mask: int, on: bool) -> bool:
        return False


class PassiveState(State):
    name = "PASSIVE"

    def on_activate(self, ctx, now):
        return ctx.transition_to(WAITING_FOR_BOARD, now)


class WaitingForBoardState(State):
    name = "WAITING_FOR_BOARD"

    def enter(self, ctx, now):
        # Covers every path into this state, e.g. an activate() request
        # that finds the board already fresh should not have to wait for
        # a further frame or tick to repoint.
        if ctx._board_fresh(now) and now >= ctx._retry_after:
            return ctx.transition_to(ACTIVATING, now)
        return []

    def on_deactivate(self, ctx, now):
        return ctx.transition_to(DEACTIVATING, now)

    def on_board_frame(self, ctx, bitmap, now):
        if now >= ctx._retry_after:
            # A frame just arrived: freshness is trivially satisfied.
            return ctx.transition_to(ACTIVATING, now)
        return []

    def on_tick(self, ctx, now):
        if ctx._board_fresh(now) and now >= ctx._retry_after:
            return ctx.transition_to(ACTIVATING, now)
        return []


class ActivatingState(State):
    name = "ACTIVATING"
    streaming = True

    def enter(self, ctx, now):
        # Adopt current state NOW: the 0x18C stream starts during
        # ACTIVATING and must already carry the right bitmap the moment
        # the board's RPDO enables on it (else relays blip).
        #
        # Adopt the panel's state as it has the memory, board does not and
	# reverts its state to zero if not pannel commands come in.
        adopted = ctx.panel_bitmap if ctx.panel_bitmap is not None else ctx.board_bitmap
        ctx.output_bitmap = adopted or 0
        return [Action.REPOINT]

    def on_repoint_succeeded(self, ctx, now):
        return ctx.transition_to(OPERATIONAL, now)

    def on_repoint_failed(self, ctx, now):
        # Set the retry timer before transitioning: WAITING_FOR_BOARD's
        # enter() checks it immediately and must see the updated value.
        ctx._retry_after = now + ctx.REPOINT_RETRY_DELAY
        return ctx.transition_to(WAITING_FOR_BOARD, now)

    def on_board_boot(self, ctx, now):
        return ctx.transition_to(WAITING_FOR_BOARD, now)

    # on_deactivate intentionally not overridden: ignored while activating.


class OperationalState(State):
    name = "OPERATIONAL"
    streaming = True

    def enter(self, ctx, now):
        ctx._last_echo_ok = now
        return []

    def on_deactivate(self, ctx, now):
        return ctx.transition_to(DEACTIVATING, now)

    def on_board_boot(self, ctx, now):
        return ctx.transition_to(WAITING_FOR_BOARD, now)

    def on_board_frame(self, ctx, bitmap, now):
        if bitmap == ctx.output_bitmap:
            ctx._last_echo_ok = now
        return []

    def on_panel_frame(self, ctx, bitmap, previous, now):
        if previous is not None and previous != bitmap:
            changed = previous ^ bitmap
            ctx.output_bitmap = (ctx.output_bitmap & ~changed) | (bitmap & changed)
        return []

    def on_tick(self, ctx, now):
        silent = (
            ctx._last_board_time is None
            or now - ctx._last_board_time > ctx.BOARD_SILENCE_TIMEOUT
        )
        mismatch = now - ctx._last_echo_ok > ctx.ECHO_MISMATCH_TIMEOUT
        if not (silent or mismatch):
            return []
        # WAITING_FOR_BOARD's enter() immediately retakes if the board is
        # still fresh (e.g. an echo mismatch with no silence).
        return ctx.transition_to(WAITING_FOR_BOARD, now)

    def set_circuit(self, ctx, mask, on):
        if on:
            ctx.output_bitmap |= mask
        else:
            ctx.output_bitmap &= ~mask
        return True


class DeactivatingState(State):
    name = "DEACTIVATING"

    def enter(self, ctx, now):
        return [Action.RELEASE]

    def on_release_done(self, ctx, now):
        return ctx.transition_to(PASSIVE, now)


# Constructed once at import time: transition_to() reassigns a reference,
# it never allocates a new state object. These are also the public
# identity you compare GatewayStateMachine.state against, e.g. `is OPERATIONAL`.
PASSIVE = PassiveState()
WAITING_FOR_BOARD = WaitingForBoardState()
ACTIVATING = ActivatingState()
OPERATIONAL = OperationalState()
DEACTIVATING = DeactivatingState()


class GatewayStateMachine:
    # Board streams every ~25 ms; thresholds calibrated on hardware 2026-07-19.
    BOARD_SILENCE_TIMEOUT = 1.0
    ECHO_MISMATCH_TIMEOUT = 0.5
    REPOINT_RETRY_DELAY = 1.0

    def __init__(self) -> None:
        self._state: State = PASSIVE
        self.output_bitmap = 0
        self.panel_bitmap: int | None = None
        self.board_bitmap: int | None = None
        self._last_board_time: float | None = None
        self._last_echo_ok: float = 0.0
        self._retry_after: float = 0.0

    @property
    def state(self) -> State:
        return self._state

    @property
    def streaming(self) -> bool:
        return self._state.streaming

    def transition_to(self, state: State, now: float) -> list[Action]:
        """The only place self._state is assigned. Runs the entered state's setup phase."""
        self._state = state
        return state.enter(self, now)

    def _board_fresh(self, now: float) -> bool:
        return (
            self._last_board_time is not None
            and now - self._last_board_time <= self.BOARD_SILENCE_TIMEOUT
        )

    # -- public API: bookkeeping (if any), then hand off to the current state

    def activate(self, now: float) -> list[Action]:
        return self._state.on_activate(self, now)

    def deactivate(self, now: float) -> list[Action]:
        return self._state.on_deactivate(self, now)

    def set_circuit(self, mask: int, on: bool) -> bool:
        """Web-originated command. Only accepted while OPERATIONAL."""
        return self._state.set_circuit(self, mask, on)

    def repoint_succeeded(self, now: float) -> None:
        self._state.on_repoint_succeeded(self, now)

    def repoint_failed(self, now: float) -> None:
        self._state.on_repoint_failed(self, now)

    def release_done(self, now: float) -> None:
        self._state.on_release_done(self, now)

    def on_panel_frame(self, bitmap: int, now: float) -> list[Action]:
        previous = self.panel_bitmap
        self.panel_bitmap = bitmap
        return self._state.on_panel_frame(self, bitmap, previous, now)

    def on_board_frame(self, bitmap: int, now: float) -> list[Action]:
        self.board_bitmap = bitmap
        self._last_board_time = now
        return self._state.on_board_frame(self, bitmap, now)

    def on_board_boot(self, now: float) -> list[Action]:
        """0x495 or 0x715 seen: the board rebooted, any repoint is gone."""
        # Reset before dispatching: WAITING_FOR_BOARD's enter() checks
        # freshness immediately, and a boot must never look "fresh".
        self._last_board_time = None  # wait for 0x20B before repointing
        return self._state.on_board_boot(self, now)

    def tick(self, now: float) -> list[Action]:
        """Call periodically (e.g. every stream period) for timeout checks."""
        return self._state.on_tick(self, now)
