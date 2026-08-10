"""Pure behavior of the panel simulator (no I/O).

The panel is a state source only (panel_od_map.md): physical buttons are
the sole way its state changes; it never adopts anything from the bus.
Startup mimics the startup2 capture: it streams all-off briefly, then
re-asserts its remembered state.
"""


class PanelCore:
    BOOT_ASSERT_DELAY = 0.2
    # Senders are 4-switch discrete rod/floats, never anything in between
    # (panel_od_map.md) -- matches gateway/calibration.py STANDARD_LEVELS.
    TANK_LEVELS = (0, 25, 50, 75, 100)
    # Fixed synthetic battery raw counts (~13.6V via
    # gateway.constants.BATTERY_VOLTS_PER_COUNT) so gateway._poll_sensors()
    # succeeds against the sim -- not independently settable here, since
    # nothing in this project currently exercises battery calibration
    # against the sim.
    STARTER_RAW = 909
    HOUSE_RAW = 909

    def __init__(self, remembered: int = 0) -> None:
        self.state = 0
        self._remembered = remembered
        self._booted_at: float | None = None
        self.freshwater_level = 0
        self.blackwater_level = 0

    def start(self, now: float) -> None:
        self._booted_at = now

    def tick(self, now: float) -> None:
        if self._booted_at is not None and now - self._booted_at >= self.BOOT_ASSERT_DELAY:
            self.state = self._remembered
            self._booted_at = None

    def press(self, mask: int) -> None:
        """A button press toggles its circuit."""
        self.state ^= mask

    def set_tank(self, tank: str, level: int) -> None:
        """tank: 'freshwater' or 'blackwater'. Mirrors the sender's fixed steps."""
        if level not in self.TANK_LEVELS:
            raise ValueError(f"level must be one of {self.TANK_LEVELS}")
        if tank == "freshwater":
            self.freshwater_level = level
        elif tank == "blackwater":
            self.blackwater_level = level
        else:
            raise ValueError(f"unknown tank: {tank}")
