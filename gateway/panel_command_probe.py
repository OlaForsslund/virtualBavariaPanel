"""Read-only-for-relays SDO probe: does the panel adopt 0x4001 if the write
alternates the alive-toggle bit, instead of a single static write?

protocol_findings.md already established that a *toggling PDO* on 0x18B with
a mismatched state is silently ignored by the panel (§ Key behavioural
findings). That test used the PDO path (0x18B) with a real per-frame stream.
This probe instead exercises repeated *SDO downloads* to 0x4001 with only the
toggle bit flipping each time -- everything else in the written value is the
panel's own current bitmap, so if adoption doesn't happen (expected), no
relay state changes either way.

Non-destructive: reads 0x4000 before/after each write to see whether the
panel's own broadcast state ever reflects what we wrote.
"""

import time

import canopen

from gateway import constants
from gateway.config import load_config
from gateway.frames import StateFrame, decode_state, encode_state, relay_names

STATE_OUT = 0x4000  # panel's broadcast state (RO, firmware-owned)
STATE_IN = 0x4001  # panel's inbox (WO, confirmed ignored for state via PDO)
WRITES = 6
DELAY_S = 0.3


def read_state(node: canopen.RemoteNode, index: int) -> StateFrame:
    raw = node.sdo.upload(index, 0)
    return decode_state(raw)


def main() -> None:
    cfg = load_config()
    network = canopen.Network()
    network.connect(interface=cfg.can_interface, channel=cfg.can_channel)
    node = network.add_node(constants.PANEL_NODE_ID)
    try:
        before = read_state(node, STATE_OUT)
        print(f"panel 0x4000 before: bitmap=0x{before.bitmap:06X} "
              f"({', '.join(relay_names(before.bitmap)) or 'all off'}) toggle={before.toggle}")

        for i in range(WRITES):
            toggle = bool(i % 2)
            data = encode_state(before.bitmap, toggle)
            try:
                node.sdo.download(STATE_IN, 0, data)
                wrote = "ok"
            except canopen.SdoAbortedError as exc:
                wrote = f"SDO abort 0x{exc.code:08X}"
            time.sleep(DELAY_S)
            after = read_state(node, STATE_OUT)
            changed = after.bitmap != before.bitmap
            print(
                f"  write {i}: 0x4001 <- {data.hex()} (toggle={toggle}) [{wrote}] "
                f"-> 0x4000 bitmap=0x{after.bitmap:06X} toggle={after.toggle} "
                f"{'CHANGED' if changed else '(unchanged)'}"
            )

        print("done — if every line reads '(unchanged)', the panel ignores 0x4001 "
              "regardless of toggle alternation, over SDO same as over PDO.")
    finally:
        network.disconnect()


if __name__ == "__main__":
    main()
