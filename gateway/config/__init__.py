"""Environment-based configuration (dev-environment.md §3)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    can_interface: str
    can_channel: str
    can_bitrate: int
    web_host: str
    web_port: int
    log_level: str
    stream_period: float  # seconds between 0x18C frames while active


def load_config(env=os.environ) -> Config:
    return Config(
        can_interface=env.get("VBP_CAN_INTERFACE", "udp_multicast"),
        can_channel=env.get("VBP_CAN_CHANNEL", "239.74.163.2"),
        can_bitrate=int(env.get("VBP_CAN_BITRATE", "250000")),
        web_host=env.get("VBP_WEB_HOST", "0.0.0.0"),
        web_port=int(env.get("VBP_WEB_PORT", "8000")),
        log_level=env.get("VBP_LOG_LEVEL", "INFO").upper(),
        # Panel cadence measured on hardware 2026-07-19: 25 ms.
        stream_period=int(env.get("VBP_STREAM_PERIOD_MS", "25")) / 1000,
    )
