#!/usr/bin/env bash
# Quick way to run the gateway against a real bus, no systemd/lighttpd
# deployment needed -- for trying it out on your own boat. Brings up can0
# and starts the gateway; the webapp + API are then served together on
# http://<this host>:8000/. Ctrl-C releases control back to the panel.
#
# Bitrate/params below match this project's confirmed bus (protocol_findings.md)
# and our CAN-FD hat's can0 -- adjust to match your own interface if it differs.
set -euo pipefail
cd "$(dirname "$0")"

sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 up type can bitrate 250000 restart-ms 1000 berr-reporting on fd off

VBP_CAN_INTERFACE=socketcan VBP_CAN_CHANNEL=can0 .venv/bin/python -m gateway.main --activate
