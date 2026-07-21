"""Pure behavior of the panel simulator (no I/O).

The panel is a state source only (panel_od_map.md): physical buttons are
the sole way its state changes; it never adopts anything from the bus.
Startup mimics the startup2 capture: it streams all-off briefly, then
re-asserts its remembered state.
"""


class PanelCore:
    BOOT_ASSERT_DELAY = 0.2

    def __init__(self, remembered: int = 0) -> None:
        self.state = 0
        self._remembered = remembered
        self._booted_at: float | None = None

    def start(self, now: float) -> None:
        self._booted_at = now

    def tick(self, now: float) -> None:
        if self._booted_at is not None and now - self._booted_at >= self.BOOT_ASSERT_DELAY:
            self.state = self._remembered
            self._booted_at = None

    def press(self, mask: int) -> None:
        """A button press toggles its circuit."""
        self.state ^= mask
