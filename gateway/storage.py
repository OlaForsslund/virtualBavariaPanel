"""JSON-file persistence for webapp config and diagnostics reports.

Independent of GatewayStateMachine -- routes using this never touch
runtime.sm, so the single-threaded state-machine constraint (CLAUDE.md)
doesn't apply here. A plain lock around file access is enough to keep
concurrent REST requests from tearing the file.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "webapp_config.json"
        self.diagnostics_path = self.data_dir / "diagnostics.jsonl"
        self._lock = threading.Lock()

    def load_config(self) -> dict:
        with self._lock:
            if not self.config_path.exists():
                return {}
            return json.loads(self.config_path.read_text())

    def save_config(self, config: dict) -> None:
        with self._lock:
            self.config_path.write_text(json.dumps(config))

    def log_diagnostics(self, report: dict, client_ip: str | None) -> None:
        record = {"received_at": time.time(), "client_ip": client_ip, **report}
        with self._lock:
            with self.diagnostics_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
