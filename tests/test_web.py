from unittest.mock import patch

from fastapi.testclient import TestClient

from gateway.command_queue import CommandQueue
from gateway.constants import RELAYS
from gateway.runtime import SensorBuffer, SensorSnapshot, StatusBuffer, StatusSnapshot
from gateway.storage import Storage
from gateway.web import _diff, create_app


class StubRuntime:
    """Only what web.py touches — a real GatewayRuntime needs a live CAN bus."""

    def __init__(self, tmp_path=None) -> None:
        self.status_buffer = StatusBuffer()
        self.sensor_buffer = SensorBuffer()
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

    switches = client.get("/status").json()["electrical"]["switches"]

    assert switches["ANCHOR"] == {"state": True}
    assert switches["BILGE_PUMP"] == {"state": True}
    assert switches["FRIDGE"] == {"state": False}
    assert set(switches) == set(RELAYS)


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


def test_put_config_merges_rather_than_replacing_other_sections(tmp_path):
    # Regression test: an earlier version replaced the whole document, so a
    # write to one section (e.g. calibration) silently wiped another (e.g.
    # visible_circuits) whenever the caller didn't resend it too.
    client = TestClient(create_app(StubRuntime(tmp_path)))
    client.put("/config", json={"visible_circuits": ["ANCHOR", "BILGE_PUMP"]})

    resp = client.put("/config", json={"calibration": {"freshwater_levels_l": {"50": 69}}})

    assert resp.status_code == 200
    config = client.get("/config").json()
    assert config["visible_circuits"] == ["ANCHOR", "BILGE_PUMP"]
    assert config["calibration"] == {"freshwater_levels_l": {"50": 69}}


def test_index_html_has_no_cache_header():
    client = TestClient(create_app(StubRuntime()))

    resp = client.get("/")

    assert resp.headers["cache-control"] == "no-cache"


def test_static_asset_is_not_given_a_no_cache_header():
    client = TestClient(create_app(StubRuntime()))

    resp = client.get("/manifest.json")

    assert "cache-control" not in resp.headers


def _sensor_snapshot(**overrides) -> SensorSnapshot:
    defaults = dict(
        starter_voltage=13.56,
        house_voltage=13.2,
        starter_raw=909,
        house_raw=883,
        freshwater_level=50,
        blackwater_level=25,
        read_at=0.0,
    )
    defaults.update(overrides)
    return SensorSnapshot(**defaults)


def test_get_sensors_before_first_reading_is_503(tmp_path):
    client = TestClient(create_app(StubRuntime(tmp_path)))

    resp = client.get("/sensors")

    assert resp.status_code == 503


def test_get_sensors_reports_tank_levels_as_a_0_1_ratio(tmp_path):
    # Liters conversion moved client-side (webapp tankLiters(), reading the
    # per-level calibration table) -- this endpoint no longer depends on
    # calibration config at all, just rescales the sender's raw 0/25/50/75/100
    # step into Signal K's 0-1 "ratio" units (signalk_alignment_plan.md §4).
    runtime = StubRuntime(tmp_path)
    runtime.sensor_buffer.snapshot = _sensor_snapshot(freshwater_level=50, blackwater_level=25)
    client = TestClient(create_app(runtime))

    body = client.get("/sensors").json()

    assert body["tanks"]["freshWater"]["currentLevel"] == 0.5
    assert body["tanks"]["blackWater"]["currentLevel"] == 0.25


def test_calibrate_battery_before_first_reading_is_503(tmp_path):
    client = TestClient(create_app(StubRuntime(tmp_path)))

    resp = client.post("/calibration/battery", json={"channel": "starter", "actual_voltage": 13.6})

    assert resp.status_code == 503


def test_calibrate_battery_computes_and_persists_factor(tmp_path):
    runtime = StubRuntime(tmp_path)
    runtime.sensor_buffer.snapshot = _sensor_snapshot(starter_raw=909)
    client = TestClient(create_app(runtime))

    resp = client.post("/calibration/battery", json={"channel": "starter", "actual_voltage": 13.6})

    assert resp.status_code == 200
    assert resp.json() == {"channel": "starter", "raw": 909, "factor": 13.6 / 909}
    assert runtime.storage.load_config()["calibration"]["battery_volts_per_count_starter"] == 13.6 / 909


def test_calibrate_battery_only_touches_its_own_channel(tmp_path):
    runtime = StubRuntime(tmp_path)
    runtime.sensor_buffer.snapshot = _sensor_snapshot(starter_raw=909, house_raw=883)
    runtime.storage.save_config({"visible_circuits": ["ANCHOR"]})
    client = TestClient(create_app(runtime))

    client.post("/calibration/battery", json={"channel": "house", "actual_voltage": 13.2})

    config = runtime.storage.load_config()
    assert config["visible_circuits"] == ["ANCHOR"]
    assert "battery_volts_per_count_starter" not in config["calibration"]
    assert config["calibration"]["battery_volts_per_count_house"] == 13.2 / 883


def test_calibrate_battery_rejects_zero_raw_reading(tmp_path):
    runtime = StubRuntime(tmp_path)
    runtime.sensor_buffer.snapshot = _sensor_snapshot(starter_raw=0)
    client = TestClient(create_app(runtime))

    resp = client.post("/calibration/battery", json={"channel": "starter", "actual_voltage": 13.6})

    assert resp.status_code == 422


def test_subscribe_sends_current_state_as_first_message(tmp_path):
    # First message is naturally a full dump: the diff starts against an
    # empty "last sent" baseline, so everything looks "changed". Harmless
    # (the client applies it like any other delta) and not relied upon --
    # per signalk_alignment_plan.md §7 the client fetches its own REST
    # snapshot on connect regardless.
    runtime = StubRuntime(tmp_path)
    runtime.status_buffer.snapshot = StatusSnapshot(
        state="OPERATIONAL",
        output_bitmap=RELAYS["ANCHOR"],
        panel_bitmap=None,
        board_bitmap=None,
        streaming=True,
    )
    runtime.sensor_buffer.snapshot = _sensor_snapshot(starter_voltage=13.6, house_voltage=13.2)
    client = TestClient(create_app(runtime))

    with patch("gateway.web.WS_POLL_PERIOD", 0.01):
        with client.websocket_connect("/subscribe") as ws:
            ws.send_json({"context": "vessels.self", "subscribe": [{"path": "electrical.switches.*"}]})
            msg = ws.receive_json()

    assert msg["context"] == "vessels.self"
    values = {v["path"]: v["value"] for v in msg["updates"][0]["values"]}
    assert values["electrical.switches.ANCHOR.state"] is True
    assert values["electrical.switches.FRIDGE.state"] is False
    assert values["electrical.batteries.starter.voltage"] == 13.6
    assert values["electrical.batteries.house.voltage"] == 13.2
    assert values["tanks.freshWater.currentLevel"] == 0.5  # _sensor_snapshot() default: freshwater_level=50
    assert values["tanks.blackWater.currentLevel"] == 0.25  # default: blackwater_level=25


def test_subscribe_sends_only_the_changed_path_on_a_later_update(tmp_path):
    runtime = StubRuntime(tmp_path)
    runtime.status_buffer.snapshot = StatusSnapshot(
        state="OPERATIONAL", output_bitmap=0, panel_bitmap=None, board_bitmap=None, streaming=True,
    )
    runtime.sensor_buffer.snapshot = _sensor_snapshot()
    client = TestClient(create_app(runtime))

    with patch("gateway.web.WS_POLL_PERIOD", 0.01):
        with client.websocket_connect("/subscribe") as ws:
            ws.send_json({"context": "vessels.self", "subscribe": []})
            ws.receive_json()  # the initial full dump (previous test covers its content)

            runtime.status_buffer.snapshot = StatusSnapshot(
                state="OPERATIONAL", output_bitmap=RELAYS["BILGE_PUMP"],
                panel_bitmap=None, board_bitmap=None, streaming=True,
            )
            msg = ws.receive_json()

    values = {v["path"]: v["value"] for v in msg["updates"][0]["values"]}
    assert values == {"electrical.switches.BILGE_PUMP.state": True}


def test_diff_is_empty_when_nothing_changed():
    assert _diff({"a": True, "b": 1.0}, {"a": True, "b": 1.0}) == {}


def test_diff_reports_only_changed_or_new_entries():
    previous = {"a": True, "b": 1.0}
    current = {"a": False, "b": 1.0, "c": 2.0}

    assert _diff(previous, current) == {"a": False, "c": 2.0}


def test_subscribe_skips_sensor_values_until_sensors_are_read(tmp_path):
    runtime = StubRuntime(tmp_path)
    runtime.status_buffer.snapshot = StatusSnapshot(
        state="OPERATIONAL", output_bitmap=0, panel_bitmap=None, board_bitmap=None, streaming=True,
    )
    # sensor_buffer.snapshot left None, as before the first sensor poll
    client = TestClient(create_app(runtime))

    with patch("gateway.web.WS_POLL_PERIOD", 0.01):
        with client.websocket_connect("/subscribe") as ws:
            ws.send_json({"context": "vessels.self", "subscribe": []})
            msg = ws.receive_json()

    paths = {v["path"] for v in msg["updates"][0]["values"]}
    assert "electrical.batteries.starter.voltage" not in paths
    assert "tanks.freshWater.currentLevel" not in paths
    assert "electrical.switches.ANCHOR.state" in paths


def test_post_diagnostics_is_logged_with_client_ip(tmp_path):
    runtime = StubRuntime(tmp_path)
    client = TestClient(create_app(runtime))

    resp = client.post("/diagnostics", json={"user_agent": "test-agent"})

    assert resp.status_code == 202
    lines = runtime.storage.diagnostics_path.read_text().splitlines()
    assert len(lines) == 1
    assert '"user_agent": "test-agent"' in lines[0]
    assert '"client_ip"' in lines[0]
