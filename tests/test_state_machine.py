from gateway.state_machine import (
    ACTIVATING,
    DEACTIVATING,
    OPERATIONAL,
    PASSIVE,
    WAITING_FOR_BOARD,
    Action,
    GatewayStateMachine,
)

CAB1 = 0x20  # CABIN_LIGHTS1
DECK = 0x80  # DECK_LIGHT


def make_operational(now: float = 0.0) -> GatewayStateMachine:
    sm = GatewayStateMachine()
    sm.on_panel_frame(CAB1, now)
    sm.on_board_frame(CAB1, now)
    assert sm.activate(now) == [Action.REPOINT]
    sm.repoint_succeeded(now)
    assert sm.state is OPERATIONAL
    return sm


def test_starts_passive():
    sm = GatewayStateMachine()
    assert sm.state is PASSIVE
    assert not sm.streaming


def test_activate_with_fresh_board_repoints_immediately():
    sm = GatewayStateMachine()
    sm.on_board_frame(0, 0.0)
    assert sm.activate(0.1) == [Action.REPOINT]
    assert sm.state is ACTIVATING
    assert sm.streaming


def test_activate_without_board_waits():
    sm = GatewayStateMachine()
    assert sm.activate(0.0) == []
    assert sm.state is WAITING_FOR_BOARD
    assert sm.on_board_frame(0, 0.5) == [Action.REPOINT]
    assert sm.state is ACTIVATING


def test_adopts_board_state_on_entering_activating():
    # Must adopt BEFORE the repoint runs: the 0x18C stream is live during
    # ACTIVATING and zeros would blip every relay off at the switchover.
    sm = GatewayStateMachine()
    sm.on_panel_frame(CAB1, 0.0)
    sm.on_board_frame(CAB1, 0.0)
    sm.activate(0.1)
    assert sm.state is ACTIVATING
    assert sm.output_bitmap == CAB1
    sm.repoint_succeeded(0.3)
    assert sm.output_bitmap == CAB1


def test_repoint_failure_retries_after_delay():
    sm = GatewayStateMachine()
    sm.on_board_frame(0, 0.0)
    sm.activate(0.0)
    sm.repoint_failed(1.0)
    assert sm.state is WAITING_FOR_BOARD
    assert sm.on_board_frame(0, 1.5) == []  # still inside retry delay
    assert sm.on_board_frame(0, 2.1) == [Action.REPOINT]


def test_web_command_only_accepted_in_operational():
    sm = GatewayStateMachine()
    assert sm.set_circuit(DECK, True) is False
    sm = make_operational()
    assert sm.set_circuit(DECK, True) is True
    assert sm.output_bitmap == CAB1 | DECK


def test_panel_edge_applies_in_operational():
    sm = make_operational(0.0)
    sm.on_panel_frame(CAB1 | DECK, 1.0)  # panel switches DECK on
    assert sm.output_bitmap == CAB1 | DECK
    sm.on_panel_frame(CAB1, 2.0)  # and off again
    assert sm.output_bitmap == CAB1


def test_panel_static_state_never_overrides_web():
    # The user scenario: panel holds CAB1 on; web turns it off; the panel's
    # unchanged stream must not turn it back on. A fresh panel *edge* must.
    sm = make_operational(0.0)
    sm.set_circuit(CAB1, False)
    assert sm.output_bitmap == 0
    sm.on_panel_frame(CAB1, 1.0)  # unchanged restatement, no edge
    assert sm.output_bitmap == 0
    sm.on_panel_frame(0, 2.0)  # panel button: off-edge (its state was on)
    sm.on_panel_frame(CAB1, 3.0)  # panel button: on-edge
    assert sm.output_bitmap == CAB1


def test_echo_lag_within_timeout_is_tolerated():
    sm = make_operational(0.0)
    sm.set_circuit(DECK, True)
    sm.on_board_frame(CAB1, 0.1)  # echo still shows old state
    assert sm.tick(0.3) == []
    assert sm.state is OPERATIONAL


def test_echo_mismatch_falls_back_and_retakes():
    sm = make_operational(0.0)
    sm.set_circuit(DECK, True)
    # Board keeps echoing the panel's state: it has reverted.
    for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        sm.on_board_frame(CAB1, t)
    assert sm.tick(0.7) == [Action.REPOINT]  # board fresh -> immediate retake
    assert sm.state is ACTIVATING


def test_board_silence_falls_back_without_repoint():
    sm = make_operational(0.0)
    assert sm.tick(1.5) == []  # silent board: fall back, nothing to repoint at
    assert sm.state is WAITING_FOR_BOARD
    assert sm.on_board_frame(CAB1, 2.0) == [Action.REPOINT]


def test_board_boot_falls_back_and_waits_for_stream():
    sm = make_operational(0.0)
    assert sm.on_board_boot(0.5) == []
    assert sm.state is WAITING_FOR_BOARD
    assert sm.tick(0.6) == []  # boot frame alone is not "alive"
    assert sm.on_board_frame(0, 1.0) == [Action.REPOINT]


def test_deactivate_releases_then_passive():
    sm = make_operational(0.0)
    assert sm.deactivate(1.0) == [Action.RELEASE]
    assert sm.state is DEACTIVATING
    assert not sm.streaming
    sm.release_done(1.2)
    assert sm.state is PASSIVE


def test_deactivate_from_waiting():
    sm = GatewayStateMachine()
    sm.activate(0.0)
    assert sm.deactivate(0.5) == [Action.RELEASE]
    sm.release_done(0.6)
    assert sm.state is PASSIVE


def test_deactivate_ignored_while_activating():
    sm = GatewayStateMachine()
    sm.on_board_frame(0, 0.0)
    sm.activate(0.0)
    assert sm.state is ACTIVATING
    assert sm.deactivate(0.1) == []
    assert sm.state is ACTIVATING


def test_passive_observes_without_acting():
    sm = GatewayStateMachine()
    sm.on_panel_frame(CAB1, 0.0)
    assert sm.on_board_frame(CAB1, 0.0) == []
    assert sm.panel_bitmap == CAB1
    assert sm.board_bitmap == CAB1
    assert sm.state is PASSIVE
