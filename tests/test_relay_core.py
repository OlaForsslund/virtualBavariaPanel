"""RelayCore must reproduce the board behavior confirmed on hardware
2026-07-19 (protocol_findings.md)."""

from simulators.relay_core import IN_PLACE_CHANGE_ABORT, INVALID_BIT, RelayCore

COB_PANEL = 0x18B
COB_GW = 0x18C
CAB1 = 0x20
DECK = 0x80


def dance(core: RelayCore, old: int, new: int) -> None:
    assert core.write_rpdo_cob(INVALID_BIT | old) is None
    assert core.write_rpdo_cob(INVALID_BIT | new) is None
    assert core.write_rpdo_cob(new) is None


def test_adopts_alternating_frames():
    core = RelayCore()
    assert core.on_state_frame(COB_PANEL, False, CAB1, 0.0) is True
    assert core.relays == CAB1
    assert core.on_state_frame(COB_PANEL, True, CAB1 | DECK, 0.025) is True
    assert core.relays == CAB1 | DECK


def test_ignores_static_alive_toggle():
    core = RelayCore()
    core.on_state_frame(COB_PANEL, True, CAB1, 0.0)
    assert core.on_state_frame(COB_PANEL, True, DECK, 0.025) is False
    assert core.relays == CAB1  # dead source ignored


def test_ignores_other_cob_ids():
    core = RelayCore()
    assert core.on_state_frame(COB_GW, False, DECK, 0.0) is False
    assert core.relays == 0


def test_in_place_cob_change_rejected_same_value_ok():
    core = RelayCore()
    assert core.write_rpdo_cob(COB_GW) == IN_PLACE_CHANGE_ABORT
    assert core.write_rpdo_cob(COB_PANEL) is None  # same-value write succeeds
    assert core.listen_cob == COB_PANEL


def test_repoint_dance_switches_source():
    core = RelayCore()
    core.on_state_frame(COB_PANEL, False, CAB1, 0.0)
    dance(core, COB_PANEL, COB_GW)
    assert core.listen_cob == COB_GW
    # panel now ignored, gateway obeyed; new source's toggle phase is
    # accepted regardless of the old source's phase
    assert core.on_state_frame(COB_PANEL, True, 0, 0.1) is False
    assert core.on_state_frame(COB_GW, False, DECK, 0.1) is True
    assert core.relays == DECK


def test_disabled_rpdo_ignores_frames():
    core = RelayCore()
    core.write_rpdo_cob(INVALID_BIT | COB_PANEL)
    assert core.on_state_frame(COB_PANEL, False, CAB1, 0.0) is False


def test_supervision_timeout_drops_all_relays():
    core = RelayCore()
    core.on_state_frame(COB_PANEL, False, CAB1, 0.0)
    core.tick(0.05)
    assert core.relays == CAB1  # short gap tolerated
    core.tick(0.25)
    assert core.relays == 0  # long interruption: everything off


def test_supervision_recovers_when_commands_resume():
    core = RelayCore()
    core.on_state_frame(COB_PANEL, False, CAB1, 0.0)
    core.tick(0.25)
    assert core.relays == 0
    assert core.on_state_frame(COB_PANEL, True, CAB1, 0.3) is True
    assert core.relays == CAB1
