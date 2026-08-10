"""Control panel simulator — CANopen node 11 on the shared (virtual) bus.

Run: python -m simulators.panel_sim [--state CABIN_LIGHTS1,WATER]
Interactive: type a relay name (or unique prefix) + Enter to "press" its
button; `tank <fresh|black> <0|25|50|75|100>` sets a tank level; empty
line lists the current state; Ctrl-C quits.
"""

import argparse
import logging
import threading

import can

from gateway import constants
from gateway.config import load_config
from gateway.frames import encode_state, relay_names
from simulators.node_base import ABORT_NO_OBJECT, SdoAbort, SimNode
from simulators.panel_core import PanelCore

log = logging.getLogger("panel_sim")


class PanelSim(SimNode):
    def __init__(self, bus: can.BusABC, stream_period: float, remembered: int) -> None:
        super().__init__(bus, constants.PANEL_NODE_ID, stream_period)
        self.core = PanelCore(remembered)

    def boot_ident(self) -> bytes:
        return b"\x01\x01\xfe\x01SIMP"

    def started(self, now: float) -> None:
        self.core.start(now)

    def tpdo_cob(self) -> int:
        return constants.COB_PANEL_STATE

    def stream_payload(self, toggle: bool, now: float) -> bytes:
        self.core.tick(now)
        return encode_state(self.core.state, toggle)

    def on_frame(self, msg: can.Message, now: float) -> None:
        pass  # state source only: adopts nothing from the bus

    def sdo_read(self, index: int, sub: int) -> bytes:
        if (index, sub) == (0x1008, 0):
            return b"SIMP"
        if (index, sub) == (constants.TANK_FRESHWATER_INDEX, constants.TANK_FRESHWATER_SUB):
            return bytes([self.core.freshwater_level])
        if (index, sub) == (constants.TANK_BLACKWATER_INDEX, constants.TANK_BLACKWATER_SUB):
            return bytes([self.core.blackwater_level])
        if (index, sub) == (constants.BATTERY_STARTER_INDEX, constants.BATTERY_STARTER_SUB):
            return PanelCore.STARTER_RAW.to_bytes(2, "little")
        if (index, sub) == (constants.BATTERY_HOUSE_INDEX, constants.BATTERY_HOUSE_SUB):
            return PanelCore.HOUSE_RAW.to_bytes(2, "little")
        raise SdoAbort(ABORT_NO_OBJECT)

    def sdo_write(self, index: int, sub: int, data: bytes) -> None:
        raise SdoAbort(ABORT_NO_OBJECT)


def parse_state(names: str) -> int:
    bitmap = 0
    for name in filter(None, (n.strip().upper() for n in names.split(","))):
        if name not in constants.RELAYS:
            raise SystemExit(f"unknown relay: {name}")
        bitmap |= constants.RELAYS[name]
    return bitmap


TANK_ALIASES = {
    "FRESH": "freshwater",
    "FRESHWATER": "freshwater",
    "BLACK": "blackwater",
    "BLACKWATER": "blackwater",
}


def button_cli(core: PanelCore) -> None:
    while True:
        try:
            entry = input().strip().upper()
        except EOFError:
            return
        if not entry:
            log.info("state: %s", ", ".join(relay_names(core.state)) or "all off")
            log.info(
                "tanks: freshwater=%d%% blackwater=%d%%",
                core.freshwater_level,
                core.blackwater_level,
            )
            continue
        parts = entry.split()
        if parts[0] == "TANK":
            tank_name = parts[1] if len(parts) > 1 else ""
            level_str = parts[2] if len(parts) > 2 else ""
            if len(parts) != 3 or tank_name not in TANK_ALIASES or not level_str.isdigit() \
                    or int(level_str) not in PanelCore.TANK_LEVELS:
                log.info("usage: tank <fresh|black> <%s>", "|".join(str(l) for l in PanelCore.TANK_LEVELS))
                continue
            tank = TANK_ALIASES[tank_name]
            level = int(level_str)
            core.set_tank(tank, level)
            log.info("%s tank -> %d%%", tank, level)
            continue
        matches = [n for n in constants.RELAYS if n.startswith(entry)]
        if len(matches) == 1:
            core.press(constants.RELAYS[matches[0]])
            log.info("pressed %s", matches[0])
        else:
            log.info("ambiguous or unknown: %s (matches: %s)", entry, matches or "none")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="", help="remembered state, comma-separated relay names")
    args = parser.parse_args()
    cfg = load_config()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(name)s %(message)s")
    log.info("panel_sim (node 11) on %s/%s", cfg.can_interface, cfg.can_channel)
    log.info("available relays: %s", ", ".join(sorted(constants.RELAYS)))
    with can.Bus(interface=cfg.can_interface, channel=cfg.can_channel) as bus:
        sim = PanelSim(bus, cfg.stream_period, parse_state(args.state))
        threading.Thread(target=button_cli, args=(sim.core,), daemon=True).start()
        try:
            sim.run()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
