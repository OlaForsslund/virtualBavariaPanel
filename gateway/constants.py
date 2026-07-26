"""Bus constants shared by gateway and simulators.

Values are findings from protocol_findings.md / panel_od_map.md, except
GATEWAY_NODE_ID which is a project choice (gives TPDO1 COB-ID 0x18C).
"""

PANEL_NODE_ID = 11  # 0x0B
BOARD_NODE_ID = 21  # 0x15
GATEWAY_NODE_ID = 12  # 0x0C

COB_PANEL_STATE = 0x18B  # panel TPDO1: relay-state command
COB_BOARD_CONFIRM = 0x20B  # board TPDO1: confirm/echo
COB_GATEWAY_STATE = 0x18C  # gateway TPDO while active
COB_PANEL_EMCY = 0x08B
COB_BOARD_EMCY = 0x095
COB_PANEL_BOOTUP = 0x70B  # one-shot NMT boot-up; no periodic heartbeat
COB_BOARD_BOOTUP = 0x715
COB_PANEL_BOOTID = 0x48B  # id/version announced at boot
COB_BOARD_BOOTID = 0x495

# Board RPDO1 COB-ID object — the repoint lever (architecture.md §4)
RPDO1_COB_ID_INDEX = 0x1400
RPDO1_COB_ID_SUB = 1

EMCY_CAN_ERROR_PASSIVE = 0x8120  # benign burst at startup

# Panel analog sensors (panel_od_map.md "Analog sensor readings", found/
# calibrated 2026-07-25). Read via SDO upload from the panel node directly —
# independent of the takeover/repoint mechanism, safe to poll in any state.
BATTERY_STARTER_INDEX = 0x2200
BATTERY_STARTER_SUB = 15
BATTERY_HOUSE_INDEX = 0x2200
BATTERY_HOUSE_SUB = 17
TANK_FRESHWATER_INDEX = 0x2501
TANK_FRESHWATER_SUB = 1
TANK_BLACKWATER_INDEX = 0x2501
TANK_BLACKWATER_SUB = 4

# Raw-count -> volts, calibrated against a trusted external voltmeter/Victron
# (13.56V / 13.61V) at raw 909, NOT the panel's own display (which read 13.8V
# for the same count — panel is ~0.2-0.24V high). Single-point calibration,
# assumes a zero-offset linear scale (panel_od_map.md).
BATTERY_VOLTS_PER_COUNT = 13.585 / 909

# Relay-state frame: 4 bytes little-endian; bit 0 is the alive toggle
# that must alternate every frame, bits 1..23 are circuits, byte 3 unused.
TOGGLE_MASK = 0x00000001
BITMAP_MASK = 0x00FFFFFE

RELAYS = {
    "ANCHOR": 0x00000002,
    "BILGE_PUMP": 0x00000004,
    "LANTERN_BOW": 0x00000008,
    "CABIN_LIGHTS2": 0x00000010,
    "CABIN_LIGHTS1": 0x00000020,
    "COMPASS_LIGHT": 0x00000040,
    "DECK_LIGHT": 0x00000080,
    "HEATER": 0x00000100,
    "LANTERN_MASTHEAD": 0x00000200,
    "INSTRUMENTS": 0x00000400,
    "MUSIC": 0x00000800,
    "FRIDGE": 0x00001000,
    "SHOWER": 0x00002000,
    "LANTERN_STEAM": 0x00004000,
    "LANTERN_AFT": 0x00008000,
    "F1": 0x00010000,
    "F2": 0x00020000,
    "F3": 0x00040000,
    "F4": 0x00080000,
    "F5": 0x00100000,
    "WATER": 0x00200000,
    "RESERVED1": 0x00400000,
    "RESERVED2": 0x00800000,
}
