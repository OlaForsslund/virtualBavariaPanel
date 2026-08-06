"""Pure calibration math for sensor readings — no I/O.

Calibration state lives in the webapp config (gateway/storage.py) as a
`calibration` dict, keyed by the constants below. Each key is optional;
absence means "not calibrated" -- battery channels fall back to the
constants.py default factor, tanks fall back to reporting the raw
level only (no liters figure).
"""

from __future__ import annotations

from gateway import constants

BATTERY_FACTOR_KEYS = {
    "starter": "battery_volts_per_count_starter",
    "house": "battery_volts_per_count_house",
}
TANK_LEVEL_KEYS = {
    "freshwater": "freshwater_levels_l",
    "blackwater": "blackwater_levels_l",
}
# The senders report one of these discrete steps, never anything in between
# (rod/float type, not continuous) -- panel_od_map.md.
STANDARD_LEVELS = (0, 25, 50, 75, 100)


def battery_factor(calibration: dict, channel: str) -> float:
    return calibration.get(BATTERY_FACTOR_KEYS[channel], constants.BATTERY_VOLTS_PER_COUNT)


def battery_voltage(raw: int, calibration: dict, channel: str) -> float:
    return round(raw * battery_factor(calibration, channel), 2)


def tank_liters(level: int, calibration: dict, tank: str) -> float | None:
    """Direct per-level lookup, no interpolation.

    A boat tank's cross-section usually isn't uniform (confirmed here:
    measured 38L/31L/45L for three successive quarters of the same tank),
    so liters-per-level are entered directly rather than assumed
    proportional to one total-capacity figure. `level` is always exactly
    one of STANDARD_LEVELS since the sender is discrete, not continuous.
    """
    levels = calibration.get(TANK_LEVEL_KEYS[tank], {})
    value = levels.get(str(level))
    return None if value is None else float(value)
