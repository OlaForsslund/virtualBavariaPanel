"""REST API: thin layer over GatewayRuntime.

Runs in its own thread, separate from the main CAN loop and the Streamer.
Per the single-threaded GatewayStateMachine constraint (CLAUDE.md), routes
must never touch `runtime.sm` or `runtime.command_queue` internals
directly — only `runtime.command_queue.submit()` to send commands and
`runtime.status_buffer.snapshot` to read state back.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gateway import calibration
from gateway.constants import RELAYS

if TYPE_CHECKING:
    # Only for the type hint below — runtime.py imports create_app, so a
    # module-level import here would be circular.
    from gateway.runtime import GatewayRuntime

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


class CircuitCommand(BaseModel):
    on: bool


class BatteryCalibration(BaseModel):
    channel: Literal["starter", "house"]
    actual_voltage: float


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
        cal = runtime.storage.load_config().get("calibration", {})
        return {
            "starter_voltage": snapshot.starter_voltage,
            "house_voltage": snapshot.house_voltage,
            # "_level", not "_pct": a discrete rod/float step (0/25/50/75/100),
            # not a true continuous percentage -- see gateway/calibration.py.
            "freshwater_level": snapshot.freshwater_level,
            "blackwater_level": snapshot.blackwater_level,
            # None (-> null) when that level hasn't been calibrated yet --
            # the client falls back to showing the raw level only.
            "freshwater_liters": calibration.tank_liters(snapshot.freshwater_level, cal, "freshwater"),
            "blackwater_liters": calibration.tank_liters(snapshot.blackwater_level, cal, "blackwater"),
        }

    @app.post("/calibration/battery")
    def calibrate_battery(body: BatteryCalibration) -> dict:
        snapshot = runtime.sensor_buffer.snapshot
        if snapshot is None:
            raise HTTPException(status_code=503, detail="sensors not read yet")
        raw = snapshot.starter_raw if body.channel == "starter" else snapshot.house_raw
        if raw == 0:
            raise HTTPException(status_code=422, detail="raw reading is zero, cannot calibrate")
        factor = body.actual_voltage / raw
        config = runtime.storage.load_config()
        config.setdefault("calibration", {})[calibration.BATTERY_FACTOR_KEYS[body.channel]] = factor
        runtime.storage.save_config(config)
        return {"channel": body.channel, "raw": raw, "factor": factor}

    @app.post("/circuits/{name}", status_code=202)
    def set_circuit(name: str, command: CircuitCommand) -> dict:
        mask = RELAYS.get(name)
        if mask is None:
            raise HTTPException(status_code=404, detail=f"unknown circuit {name!r}")
        # Fire-and-forget: the main loop applies this on its next drain();
        # the client reads back the result via GET /status, not this response.
        runtime.command_queue.submit(lambda: runtime.cmd_set_circuit(mask, command.on))
        return {"circuit": name, "requested": command.on}

    @app.get("/config")
    def get_webapp_config() -> dict:
        return runtime.storage.load_config()

    @app.put("/config")
    def set_webapp_config(config: dict) -> dict:
        # Shallow-merges at the top level rather than replacing the whole
        # document: config now holds independent sections (visible_circuits,
        # calibration, ...), and a full replace lets a write to one silently
        # wipe another whenever the caller doesn't also resend it.
        current = runtime.storage.load_config()
        current.update(config)
        runtime.storage.save_config(current)
        return current

    @app.post("/diagnostics", status_code=202)
    def post_diagnostics(report: dict, request: Request) -> dict:
        client_ip = request.client.host if request.client else None
        runtime.storage.log_diagnostics(report, client_ip)
        return {"status": "logged"}

    @app.post("/system/restart", status_code=202)
    def restart_system() -> dict:
        # Fire-and-forget, non-blocking: `systemctl reboot` returns once the
        # shutdown is queued, well before the Pi actually goes down, so the
        # HTTP response still reaches the browser. `ola` has passwordless
        # sudo on this box already (deploy prerequisite, not set up here).
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        return {"status": "restarting"}

    @app.middleware("http")
    async def no_cache_html(request: Request, call_next):
        # StaticFiles sends no Cache-Control at all (only ETag/Last-Modified),
        # which lets browsers heuristically cache index.html and silently
        # keep serving a stale copy after a deploy -- caught on the MFD
        # 2026-08-06, where its "Reload" button appeared to do nothing.
        # Static assets (images, manifest) are fine to cache normally, so
        # this only touches HTML responses.
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Serves the webapp directly so `gateway.main --activate` alone is enough
    # to try it out — the full boat deployment fronts this with lighttpd
    # instead (deploy/etc/lighttpd/conf-available/20-vbp-proxy.conf), which
    # serves webapp/ itself and only proxies the API routes above, never
    # reaching this mount. Registered last so it doesn't shadow them.
    app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")

    return app
