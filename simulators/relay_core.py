"""Pure behavior of the relay board simulator (no I/O).

Models the CODEVICE board as observed in protocol_findings.md:
- obeys state frames on its RPDO COB-ID only while the RPDO is enabled,
  and only from a source whose alive toggle alternates frame to frame;
- `1400:1` is volatile: same-value writes succeed, changing the id
  in-place is rejected (abort 0x06090030), the invalid-bit dance works;
- command supervision: if valid commands stop arriving, all relays drop
  (observed on hardware; exact threshold unmeasured, between ~10 ms and
  ~150 ms — the simulator uses 100 ms).
"""

from gateway import constants

INVALID_BIT = 0x80000000
IN_PLACE_CHANGE_ABORT = 0x06090030
COB_ID_MASK = 0x7FF


class RelayCore:
    SUPERVISION_TIMEOUT = 0.1

    def __init__(self) -> None:
        self.relays = 0
        self.rpdo_cob_value = constants.COB_PANEL_STATE  # volatile factory default
        self._last_toggle: bool | None = None
        self._last_command: float | None = None

    @property
    def enabled(self) -> bool:
        return not self.rpdo_cob_value & INVALID_BIT

    @property
    def listen_cob(self) -> int:
        return self.rpdo_cob_value & COB_ID_MASK

    def on_state_frame(self, cob: int, toggle: bool, bitmap: int, now: float) -> bool:
        """Returns True if the command was adopted."""
        if not self.enabled or cob != self.listen_cob:
            return False
        if self._last_toggle is not None and toggle == self._last_toggle:
            return False  # static alive toggle: dead source, ignore
        self._last_toggle = toggle
        self._last_command = now
        self.relays = bitmap
        return True

    def tick(self, now: float) -> None:
        """Command supervision: interruption drops all relays."""
        if self._last_command is not None and now - self._last_command > self.SUPERVISION_TIMEOUT:
            self.relays = 0
            self._last_command = None

    def write_rpdo_cob(self, value: int) -> int | None:
        """SDO write to 1400:1. Returns an SDO abort code, or None on success."""
        id_changed = (value & COB_ID_MASK) != self.listen_cob
        if id_changed and not value & INVALID_BIT:
            return IN_PLACE_CHANGE_ABORT
        if id_changed:
            self._last_toggle = None  # new source: alive-toggle phase unknown
        self.rpdo_cob_value = value
        return None
