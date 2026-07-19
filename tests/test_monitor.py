"""Replays the real startup2 capture through the monitor and checks that
the decoded story matches what protocol_findings.md describes."""

import re
from pathlib import Path

from gateway.monitor import BusMonitor

CAPTURE = Path(__file__).resolve().parent.parent / "startup2"
LINE = re.compile(r"can\d+\s+([0-9A-Fa-f]+)\s+\[\d\]\s+((?:[0-9A-Fa-f]{2}\s*)+)")


def capture_frames():
    for line in CAPTURE.read_text().splitlines():
        m = LINE.search(line)
        if m:
            yield int(m.group(1), 16), bytes.fromhex(m.group(2).replace(" ", ""))


def test_startup2_replay():
    monitor = BusMonitor()
    events = []
    for cob_id, data in capture_frames():
        events.extend(monitor.on_frame(cob_id, data))

    # Boot markers for both nodes
    assert "board: NMT boot-up" in events
    assert "panel: NMT boot-up" in events
    assert any(e.startswith("board: boot id/version") for e in events)
    assert any(e.startswith("panel: boot id/version") for e in events)

    # Startup EMCY noise decoded and flagged benign
    assert any("EMCY code=0x8120" in e and "benign" in e for e in events)

    # Both nodes start at all-off; panel then re-asserts its remembered
    # state (CABIN_LIGHTS2) and the board adopts it.
    assert "board: initial state — all off" in events
    assert "panel: initial state — all off" in events
    assert "panel: CABIN_LIGHTS2 -> ON" in events
    assert "board: CABIN_LIGHTS2 -> ON" in events
    assert monitor.panel_bitmap == 0x10
    assert monitor.board_bitmap == 0x10


def test_toggle_alternation_produces_no_phantom_events():
    monitor = BusMonitor()
    events = []
    # Same state, alternating toggle bit — must yield only the initial event.
    for data in (b"\x00\x00\x00\x00", b"\x01\x00\x00\x00", b"\x00\x00\x00\x00"):
        events.extend(monitor.on_frame(0x20B, data))
    assert events == ["board: initial state — all off"]
