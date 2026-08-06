from unittest.mock import patch

from fastapi.testclient import TestClient

from gateway.command_queue import CommandQueue
from gateway.constants import RELAYS
from gateway.runtime import StatusBuffer, StatusSnapshot
from gateway.storage import Storage
from gateway.web import create_app


class StubRuntime:
    """Only what web.py touches — a real GatewayRuntime needs a live CAN bus."""

    def __init__(self, tmp_path=None) -> None:
        self.status_buffer = StatusBuffer()
        self.command_queue = CommandQueue()
        self.storage = Storage(tmp_path) if tmp_path is not None else None
        self.circuit_calls: list[tuple[int, bool]] = []

    def cmd_set_circuit(self, mask: int, on: bool) -> None:
        self.circuit_calls.append((mask, on))


def test_status_before_first_snapshot_is_503():
    client = TestClient(create_app(StubRuntime()))

    resp = client.get("/status")

    assert resp.status_code == 503


def test_status_reports_snapshot_fields():
    runtime = StubRuntime()
    runtime.status_buffer.snapshot = StatusSnapshot(
        state="OPERATIONAL",
        output_bitmap=RELAYS["ANCHOR"] | RELAYS["BILGE_PUMP"],
        panel_bitmap=RELAYS["ANCHOR"],
        board_bitmap=RELAYS["ANCHOR"],
        streaming=True,
    )
    client = TestClient(create_app(runtime))

    body = client.get("/status").json()

    assert body["state"] == "OPERATIONAL"
    assert body["streaming"] is True
    assert body["panel_bitmap"] == RELAYS["ANCHOR"]
    assert body["board_bitmap"] == RELAYS["ANCHOR"]


def test_status_circuits_are_named_and_reflect_the_bitmap():
    runtime = StubRuntime()
    runtime.status_buffer.snapshot = StatusSnapshot(
        state="OPERATIONAL",
        output_bitmap=RELAYS["ANCHOR"] | RELAYS["BILGE_PUMP"],
        panel_bitmap=None,
        board_bitmap=None,
        streaming=True,
    )
    client = TestClient(create_app(runtime))

    circuits = client.get("/status").json()["circuits"]

    assert circuits["ANCHOR"] is True
    assert circuits["BILGE_PUMP"] is True
    assert circuits["FRIDGE"] is False
    assert set(circuits) == set(RELAYS)


def test_post_circuit_queues_a_command_it_does_not_run_it_inline():
    runtime = StubRuntime()
    client = TestClient(create_app(runtime))

    resp = client.post("/circuits/ANCHOR", json={"on": True})

    assert resp.status_code == 202
    assert resp.json() == {"circuit": "ANCHOR", "requested": True}
    assert runtime.circuit_calls == []  # not run yet — only queued


def test_post_circuit_command_runs_on_drain_with_the_right_mask():
    runtime = StubRuntime()
    client = TestClient(create_app(runtime))

    client.post("/circuits/BILGE_PUMP", json={"on": False})
    runtime.command_queue.drain()

    assert runtime.circuit_calls == [(RELAYS["BILGE_PUMP"], False)]


def test_post_unknown_circuit_is_404_and_queues_nothing():
    runtime = StubRuntime()
    client = TestClient(create_app(runtime))

    resp = client.post("/circuits/NOT_A_CIRCUIT", json={"on": True})

    assert resp.status_code == 404
    assert runtime.command_queue.drain() == 0


def test_post_circuit_rejects_a_missing_body():
    client = TestClient(create_app(StubRuntime()))

    resp = client.post("/circuits/ANCHOR", json={})

    assert resp.status_code == 422


def test_post_system_restart_shells_out_to_systemctl_reboot():
    client = TestClient(create_app(StubRuntime()))

    with patch("gateway.web.subprocess.Popen") as mock_popen:
        resp = client.post("/system/restart")

    assert resp.status_code == 202
    mock_popen.assert_called_once_with(["sudo", "systemctl", "reboot"])


def test_get_config_is_empty_dict_before_anything_saved(tmp_path):
    client = TestClient(create_app(StubRuntime(tmp_path)))

    assert client.get("/config").json() == {}


def test_put_config_then_get_round_trips(tmp_path):
    client = TestClient(create_app(StubRuntime(tmp_path)))

    put_resp = client.put("/config", json={"visible_circuits": ["ANCHOR"]})

    assert put_resp.status_code == 200
    assert client.get("/config").json() == {"visible_circuits": ["ANCHOR"]}


def test_index_html_has_no_cache_header():
    client = TestClient(create_app(StubRuntime()))

    resp = client.get("/")

    assert resp.headers["cache-control"] == "no-cache"


def test_static_asset_is_not_given_a_no_cache_header():
    client = TestClient(create_app(StubRuntime()))

    resp = client.get("/manifest.json")

    assert "cache-control" not in resp.headers


def test_post_diagnostics_is_logged_with_client_ip(tmp_path):
    runtime = StubRuntime(tmp_path)
    client = TestClient(create_app(runtime))

    resp = client.post("/diagnostics", json={"user_agent": "test-agent"})

    assert resp.status_code == 202
    lines = runtime.storage.diagnostics_path.read_text().splitlines()
    assert len(lines) == 1
    assert '"user_agent": "test-agent"' in lines[0]
    assert '"client_ip"' in lines[0]
