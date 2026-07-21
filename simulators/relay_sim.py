"""Relay board simulator — CANopen node 21 on the shared (virtual) bus.

Run: python -m simulators.relay_sim   (config via VBP_* env vars)
"""

import logging

import can

from gateway import constants
from gateway.config import load_config
from gateway.frames import decode_state, encode_state, relay_names
from simulators.node_base import ABORT_NO_OBJECT, ABORT_READ_ONLY, SdoAbort, SimNode
from simulators.relay_core import RelayCore

log = logging.getLogger("relay_sim")


class RelaySim(SimNode):
    def __init__(self, bus: can.BusABC, stream_period: float) -> None:
        super().__init__(bus, constants.BOARD_NODE_ID, stream_period)
        self.core = RelayCore()

    def boot_ident(self) -> bytes:
        return b"\x03\x01\xfe\x01SIMR"

    def tpdo_cob(self) -> int:
        return constants.COB_BOARD_CONFIRM

    def stream_payload(self, toggle: bool, now: float) -> bytes:
        before = self.core.relays
        self.core.tick(now)
        if self.core.relays != before:
            log.info("supervision timeout — all relays dropped")
        return encode_state(self.core.relays, toggle)

    def on_frame(self, msg: can.Message, now: float) -> None:
        if len(msg.data) != 4 or msg.arbitration_id == constants.COB_BOARD_CONFIRM:
            return
        frame = decode_state(bytes(msg.data))
        before = self.core.relays
        if self.core.on_state_frame(msg.arbitration_id, frame.toggle, frame.bitmap, now):
            if self.core.relays != before:
                log.info("relays: %s", ", ".join(relay_names(self.core.relays)) or "all off")

    def sdo_read(self, index: int, sub: int) -> bytes:
        if (index, sub) == (constants.RPDO1_COB_ID_INDEX, constants.RPDO1_COB_ID_SUB):
            return self.core.rpdo_cob_value.to_bytes(4, "little")
        if (index, sub) == (0x1008, 0):
            return b"SIMR"
        raise SdoAbort(ABORT_NO_OBJECT)

    def sdo_write(self, index: int, sub: int, data: bytes) -> None:
        if (index, sub) == (constants.RPDO1_COB_ID_INDEX, constants.RPDO1_COB_ID_SUB):
            abort = self.core.write_rpdo_cob(int.from_bytes(data, "little"))
            if abort is not None:
                raise SdoAbort(abort)
            log.info("1400:1 = 0x%08X", self.core.rpdo_cob_value)
            return
        raise SdoAbort(ABORT_READ_ONLY)


def main() -> None:
    cfg = load_config()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(name)s %(message)s")
    log.info("relay_sim (node 21) on %s/%s", cfg.can_interface, cfg.can_channel)
    with can.Bus(interface=cfg.can_interface, channel=cfg.can_channel) as bus:
        try:
            RelaySim(bus, cfg.stream_period).run()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
