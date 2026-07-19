"""Gateway entry point. Currently: passive monitor mode — opens the bus
listen-only, decodes traffic, logs named relay changes. Sends nothing."""

import logging

import can

from gateway.config import load_config
from gateway.monitor import BusMonitor

log = logging.getLogger("gateway")


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info(
        "monitor mode: listening on %s/%s (transmitting nothing)",
        cfg.can_interface,
        cfg.can_channel,
    )
    monitor = BusMonitor()
    with can.Bus(interface=cfg.can_interface, channel=cfg.can_channel) as bus:
        for msg in bus:
            for event in monitor.on_frame(msg.arbitration_id, bytes(msg.data)):
                log.info(event)


if __name__ == "__main__":
    main()
