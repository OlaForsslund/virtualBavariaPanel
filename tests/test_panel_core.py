from simulators.panel_core import PanelCore

CAB1 = 0x20
WATER = 0x200000


def test_boot_reasserts_remembered_state():
    core = PanelCore(remembered=CAB1 | WATER)
    core.start(0.0)
    core.tick(0.1)
    assert core.state == 0  # streams all-off first, like startup2
    core.tick(0.3)
    assert core.state == CAB1 | WATER


def test_press_toggles():
    core = PanelCore()
    core.press(CAB1)
    assert core.state == CAB1
    core.press(CAB1)
    assert core.state == 0
