#!/usr/bin/env bash
# Quick way to run the full dev-loop stack (relay_sim + panel_sim + gateway)
# with one command instead of three terminals -- see dev-environment.md §5
# for what each piece does. No real bus/hardware needed: config defaults to
# python-can's udp_multicast backend.
#
# relay_sim and the gateway run in the background, logged to /tmp; panel_sim
# runs in the foreground since it's the interactive one (type a relay name +
# Enter to simulate a button press). Ctrl-C, or just exiting panel_sim,
# tears down the other two via the trap below. Webapp + API then live at
# http://localhost:8000/ (dev.zeus3_7_preview.html included, see
# dev-environment.md).
set -euo pipefail
cd "$(dirname "$0")"

RELAY_LOG="$(mktemp -t vbp-relay_sim.XXXXXX.log)"
GATEWAY_LOG="$(mktemp -t vbp-gateway.XXXXXX.log)"

.venv/bin/python -m simulators.relay_sim > "$RELAY_LOG" 2>&1 &
RELAY_PID=$!

.venv/bin/python -m gateway.main --activate > "$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!

cleanup() {
    kill "$RELAY_PID" "$GATEWAY_PID" 2>/dev/null || true
    wait "$RELAY_PID" "$GATEWAY_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "relay_sim (pid $RELAY_PID) -> $RELAY_LOG"
echo "gateway   (pid $GATEWAY_PID) -> $GATEWAY_LOG"
echo "webapp + API: http://localhost:${VBP_WEB_PORT:-8000}/"
echo
echo "panel_sim is interactive below -- type a relay name + Enter to simulate a button press."
echo

.venv/bin/python -m simulators.panel_sim
