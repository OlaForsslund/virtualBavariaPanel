from gateway import calibration, constants


def test_battery_factor_falls_back_to_constants_default_when_uncalibrated():
    assert calibration.battery_factor({}, "starter") == constants.BATTERY_VOLTS_PER_COUNT
    assert calibration.battery_factor({}, "house") == constants.BATTERY_VOLTS_PER_COUNT


def test_battery_factor_uses_calibrated_value_when_present():
    cal = {"battery_volts_per_count_starter": 0.02}

    assert calibration.battery_factor(cal, "starter") == 0.02
    assert calibration.battery_factor(cal, "house") == constants.BATTERY_VOLTS_PER_COUNT


def test_battery_voltage_applies_the_resolved_factor():
    cal = {"battery_volts_per_count_starter": 0.01}

    assert calibration.battery_voltage(900, cal, "starter") == 9.0


def test_battery_calibration_is_independent_per_channel():
    cal = {
        "battery_volts_per_count_starter": 0.01,
        "battery_volts_per_count_house": 0.02,
    }

    assert calibration.battery_voltage(900, cal, "starter") == 9.0
    assert calibration.battery_voltage(900, cal, "house") == 18.0


def test_tank_liters_is_none_when_uncalibrated():
    assert calibration.tank_liters(50, {}, "freshwater") is None


def test_tank_liters_is_a_direct_per_level_lookup_not_an_interpolation():
    # Real measurements from a non-uniform tank: 38L/31L/45L for three
    # successive quarters -- proportional scaling from one capacity figure
    # would get this wrong, so each level is looked up directly.
    cal = {"freshwater_levels_l": {"0": 0, "25": 38, "50": 69, "75": 114}}

    assert calibration.tank_liters(0, cal, "freshwater") == 0.0
    assert calibration.tank_liters(25, cal, "freshwater") == 38.0
    assert calibration.tank_liters(50, cal, "freshwater") == 69.0
    assert calibration.tank_liters(75, cal, "freshwater") == 114.0


def test_tank_liters_is_none_for_a_level_not_yet_calibrated():
    # 100% not measured yet -- falls back to % display for that level only,
    # even though 0/25/50/75 are already calibrated.
    cal = {"freshwater_levels_l": {"0": 0, "25": 38, "50": 69, "75": 114}}

    assert calibration.tank_liters(100, cal, "freshwater") is None


def test_tank_liters_is_independent_per_tank():
    cal = {
        "freshwater_levels_l": {"50": 69},
        "blackwater_levels_l": {"50": 40},
    }

    assert calibration.tank_liters(50, cal, "freshwater") == 69.0
    assert calibration.tank_liters(50, cal, "blackwater") == 40.0
