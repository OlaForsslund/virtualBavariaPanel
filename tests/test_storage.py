from gateway.storage import Storage


def test_load_config_is_empty_dict_before_anything_saved(tmp_path):
    storage = Storage(tmp_path)

    assert storage.load_config() == {}


def test_save_config_then_load_round_trips(tmp_path):
    storage = Storage(tmp_path)

    storage.save_config({"visible_circuits": ["ANCHOR", "BILGE_PUMP"]})

    assert storage.load_config() == {"visible_circuits": ["ANCHOR", "BILGE_PUMP"]}


def test_save_config_overwrites_previous_value(tmp_path):
    storage = Storage(tmp_path)

    storage.save_config({"visible_circuits": ["ANCHOR"]})
    storage.save_config({"visible_circuits": ["FRIDGE"]})

    assert storage.load_config() == {"visible_circuits": ["FRIDGE"]}


def test_log_diagnostics_appends_jsonl_with_client_ip(tmp_path):
    storage = Storage(tmp_path)

    storage.log_diagnostics({"user_agent": "test-agent"}, "10.42.0.80")
    storage.log_diagnostics({"user_agent": "test-agent-2"}, "10.42.0.80")

    lines = storage.diagnostics_path.read_text().splitlines()
    assert len(lines) == 2
    import json

    first = json.loads(lines[0])
    assert first["user_agent"] == "test-agent"
    assert first["client_ip"] == "10.42.0.80"
    assert "received_at" in first


def test_data_dir_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"

    Storage(nested)

    assert nested.is_dir()
