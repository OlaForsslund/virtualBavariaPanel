"""Decoding of the 4-byte relay-state frame (protocol_findings.md)."""

from dataclasses import dataclass

from gateway.constants import BITMAP_MASK, RELAYS, TOGGLE_MASK


@dataclass(frozen=True)
class StateFrame:
    toggle: bool
    bitmap: int  # circuit bits only, toggle masked out


def decode_state(data: bytes) -> StateFrame:
    if len(data) != 4:
        raise ValueError(f"relay-state frame must be 4 bytes, got {len(data)}")
    raw = int.from_bytes(data, "little")
    return StateFrame(toggle=bool(raw & TOGGLE_MASK), bitmap=raw & BITMAP_MASK)


def encode_state(bitmap: int, toggle: bool) -> bytes:
    raw = (bitmap & BITMAP_MASK) | (TOGGLE_MASK if toggle else 0)
    return raw.to_bytes(4, "little")


def relay_names(bitmap: int) -> list[str]:
    return [name for name, mask in RELAYS.items() if bitmap & mask]


def changes(old: int, new: int) -> list[tuple[str, bool]]:
    """Named circuits that differ between two bitmaps, with their new value."""
    diff = old ^ new
    return [(name, bool(new & mask)) for name, mask in RELAYS.items() if diff & mask]
