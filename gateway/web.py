"""REST API: thin layer over GatewayRuntime.

Runs in its own thread, separate from the main CAN loop and the Streamer.
Per the single-threaded GatewayStateMachine constraint (CLAUDE.md), routes
must never touch `runtime.sm` or `runtime.command_queue` internals
directly — only `runtime.command_queue.submit()` to send commands and
`runtime.status_buffer.snapshot` to read state back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gateway.constants import RELAYS

if TYPE_CHECKING:
    # Only for the type hint below — runtime.py imports create_app, so a
    # module-level import here would be circular.
    from gateway.runtime import GatewayRuntime

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


class CircuitCommand(BaseModel):
    on: bool


def create_app(runtime: GatewayRuntime) -> FastAPI:
    app = FastAPI(title="Virtual Bavaria Panel")

    @app.get("/status")
    def get_status() -> dict:
        snapshot = runtime.status_buffer.snapshot
        if snapshot is None:
            raise HTTPException(status_code=503, detail="gateway not ready")
        return {
            "state": snapshot.state,
            "streaming": snapshot.streaming,
            "output_bitmap": snapshot.output_bitmap,
            "panel_bitmap": snapshot.panel_bitmap,
            "board_bitmap": snapshot.board_bitmap,
            "circuits": {
                name: bool(snapshot.output_bitmap & mask)
                for name, mask in RELAYS.items()
            },
        }

    @app.get("/sensors")
    def get_sensors() -> dict:
        snapshot = runtime.sensor_buffer.snapshot
        if snapshot is None:
            raise HTTPException(status_code=503, detail="sensors not read yet")
        return {
            "starter_voltage": snapshot.starter_voltage,
            "house_voltage": snapshot.house_voltage,
            "freshwater_pct": snapshot.freshwater_pct,
            "blackwater_pct": snapshot.blackwater_pct,
        }

    @app.post("/circuits/{name}", status_code=202)
    def set_circuit(name: str, command: CircuitCommand) -> dict:
        mask = RELAYS.get(name)
        if mask is None:
            raise HTTPException(status_code=404, detail=f"unknown circuit {name!r}")
        # Fire-and-forget: the main loop applies this on its next drain();
        # the client reads back the result via GET /status, not this response.
        runtime.command_queue.submit(lambda: runtime.cmd_set_circuit(mask, command.on))
        return {"circuit": name, "requested": command.on}

    # Serves the webapp directly so `gateway.main --activate` alone is enough
    # to try it out — the full boat deployment fronts this with lighttpd
    # instead (deploy/etc/lighttpd/conf-available/20-vbp-proxy.conf), which
    # serves webapp/ itself and only proxies the API routes above, never
    # reaching this mount. Registered last so it doesn't shadow them.
    app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")

    return app
