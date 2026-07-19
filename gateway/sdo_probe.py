"""Read-only SDO probe of a bus node (default: the relay board).

Exercises the SDO request/response path that the takeover sequence will
use. Sends only SDO upload requests; changes nothing.
"""

import argparse

import canopen

from gateway import constants
from gateway.config import load_config

READS = [
    (0x1008, 0, "str", "device name"),
    (0x1009, 0, "str", "hw version"),
    (0x100A, 0, "str", "sw version"),
    (constants.RPDO1_COB_ID_INDEX, constants.RPDO1_COB_ID_SUB, "u32", "RPDO1 COB-ID"),
]


def fmt(raw: bytes, kind: str) -> str:
    if kind == "str":
        return raw.decode("ascii", "replace").strip("\x00 ")
    return f"0x{int.from_bytes(raw, 'little'):08X}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", type=int, default=constants.BOARD_NODE_ID)
    args = parser.parse_args()
    cfg = load_config()

    network = canopen.Network()
    network.connect(interface=cfg.can_interface, channel=cfg.can_channel)
    try:
        node = network.add_node(args.node)
        print(f"node {args.node}:")
        for index, sub, kind, label in READS:
            try:
                raw = node.sdo.upload(index, sub)
                print(f"  {index:04X}:{sub} {label:13} = {fmt(raw, kind)}")
            except canopen.SdoAbortedError as exc:
                print(f"  {index:04X}:{sub} {label:13} : SDO abort 0x{exc.code:08X}")
            except canopen.SdoCommunicationError as exc:
                print(f"  {index:04X}:{sub} {label:13} : no/invalid response ({exc})")
    finally:
        network.disconnect()


if __name__ == "__main__":
    main()
