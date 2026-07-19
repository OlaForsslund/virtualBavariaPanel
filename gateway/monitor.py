"""Passive decoder of bus traffic into human-readable events.

Pure logic (no python-can): feed it (cob_id, data) pairs, get event strings.
This is the observation core of the PASSIVE state (architecture.md §6);
panel_interface/relay_interface will build on the same decoding.
"""

from gateway import constants
from gateway.frames import changes, decode_state, relay_names


class BusMonitor:
    def __init__(self) -> None:
        self._bitmaps: dict[str, int | None] = {"panel": None, "board": None}

    @property
    def panel_bitmap(self) -> int | None:
        return self._bitmaps["panel"]

    @property
    def board_bitmap(self) -> int | None:
        return self._bitmaps["board"]

    def on_frame(self, cob_id: int, data: bytes) -> list[str]:
        match cob_id:
            case constants.COB_PANEL_STATE:
                return self._on_state("panel", data)
            case constants.COB_BOARD_CONFIRM:
                return self._on_state("board", data)
            case constants.COB_PANEL_BOOTUP:
                return ["panel: NMT boot-up"]
            case constants.COB_BOARD_BOOTUP:
                return ["board: NMT boot-up"]
            case constants.COB_PANEL_BOOTID:
                return [f"panel: boot id/version {data.hex(' ')}"]
            case constants.COB_BOARD_BOOTID:
                return [f"board: boot id/version {data.hex(' ')}"]
            case constants.COB_PANEL_EMCY:
                return self._on_emcy("panel", data)
            case constants.COB_BOARD_EMCY:
                return self._on_emcy("board", data)
            case _:
                return []

    def _on_state(self, who: str, data: bytes) -> list[str]:
        frame = decode_state(data)
        last = self._bitmaps[who]
        self._bitmaps[who] = frame.bitmap
        if last is None:
            on = ", ".join(relay_names(frame.bitmap)) or "all off"
            return [f"{who}: initial state — {on}"]
        return [
            f"{who}: {name} -> {'ON' if value else 'OFF'}"
            for name, value in changes(last, frame.bitmap)
        ]

    def _on_emcy(self, who: str, data: bytes) -> list[str]:
        code = int.from_bytes(data[0:2], "little")
        register = data[2] if len(data) > 2 else 0
        note = (
            " (CAN error passive — benign at startup)"
            if code == constants.EMCY_CAN_ERROR_PASSIVE
            else ""
        )
        return [f"{who}: EMCY code=0x{code:04X} reg=0x{register:02X}{note}"]
