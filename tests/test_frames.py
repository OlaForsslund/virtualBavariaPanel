import pytest

from gateway.frames import changes, decode_state, encode_state, relay_names


def test_decode_toggle_and_bitmap():
    frame = decode_state(bytes([0x11, 0x00, 0x00, 0x00]))
    assert frame.toggle is True
    assert frame.bitmap == 0x10


def test_decode_toggle_off():
    frame = decode_state(bytes([0x10, 0x00, 0x00, 0x00]))
    assert frame.toggle is False
    assert frame.bitmap == 0x10


def test_decode_rejects_wrong_length():
    with pytest.raises(ValueError):
        decode_state(bytes([0x00]))


def test_encode_roundtrip():
    data = encode_state(0x200010, toggle=True)
    frame = decode_state(data)
    assert frame.bitmap == 0x200010
    assert frame.toggle is True


def test_encode_masks_toggle_out_of_bitmap():
    assert decode_state(encode_state(0xFFFFFF, toggle=False)).toggle is False


def test_relay_names():
    assert relay_names(0x10) == ["CABIN_LIGHTS2"]
    assert relay_names(0x24) == ["BILGE_PUMP", "CABIN_LIGHTS1"]
    assert relay_names(0) == []


def test_changes():
    assert changes(0x00, 0x10) == [("CABIN_LIGHTS2", True)]
    assert changes(0x30, 0x10) == [("CABIN_LIGHTS1", False)]
    assert changes(0x10, 0x10) == []
