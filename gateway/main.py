"""Gateway entry point.

Default: passive — observes the bus and logs decoded events, transmits
nothing. With --activate: takes over the relay board on startup and
mediates (panel edges keep working through the gateway). Ctrl-C / SIGINT
releases control back to the panel before exiting.
"""

import argparse
import logging

from gateway.config import load_config
from gateway.runtime import GatewayRuntime

log = logging.getLogger("gateway")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="take over the relay board on startup",
    )
    args = parser.parse_args()
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("gateway starting on %s/%s", cfg.can_interface, cfg.can_channel)

    runtime = GatewayRuntime(cfg)
    if args.activate:
        runtime.activate()
    try:
        runtime.run()
    except KeyboardInterrupt:
        log.info("interrupted — shutting down")
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
