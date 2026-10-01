#!/usr/bin/env python3
"""Temporary MFD app tiles for perf experiments.

Same multicast announce as /usr/local/bin/mfd-app-announce.py (239.2.1.1:2053,
every 10 s), but one tile per VARIANTS entry, each with its own Source ID.
Stop the process and the tiles drop off the MFD.

How the Zeus3 treats tiles (observed 2026-10-01):
- It drops the #fragment from the URL and appends its own query params
  (mfd_name, mfd_model_detail, lang, mode, brand) -- select pages/variants
  with query params, never with #hash.
- Re-opening a tile resumes the page it already has; to force a fresh load,
  give the tile a new Source ID and URL.
- Every page it has opened stays alive in the background (still connected,
  still running JS, though no longer painted) until the plotter restarts --
  restart it before a clean measurement run.
- Touch and key input sent remotely (Hermes / port 6633) doesn't reach the
  web page, only the plotter's own UI.
"""
import json
import socket
import subprocess
import time

MCAST_GROUP = "239.2.1.1"
MCAST_PORT = 2053
APP_PORT = 80
ICON_PATH = "/android-chrome-192x192.png"

# (Source ID, tile name, path) -- e.g. a page under webapp/dev/ that loads
# /dev/perf/perf-probe.js as its first script.
VARIANTS = [
    ("vbp-perf-1", "VBP perf 1", "/dev/baseline/?run1"),
]


def get_ipv4_addrs():
    out = subprocess.run(
        ["ip", "-o", "-4", "addr", "show", "scope", "global"],
        capture_output=True, text=True,
    ).stdout
    addrs = []
    for line in out.splitlines():
        parts = line.split()
        for i, p in enumerate(parts):
            if p == "inet":
                addrs.append(parts[i + 1].split("/")[0])
    return addrs


def build_payload(ip, source, name, path):
    return {
        "Source": source,
        "IP": ip,
        "Text": [{"Language": "en", "Name": name, "Description": f"VBP perf experiment: {path}"}],
        "Icon": f"http://{ip}:{APP_PORT}{ICON_PATH}",
        "URL": f"http://{ip}:{APP_PORT}{path}",
        "OnlyShowOnClientIP": "false",
        "BrowserPanel": {
            "Enable": True,
            "ProgressBarEnable": False,
            "MenuText": [{"Language": "en", "Name": "Home"}],
        },
    }


def main():
    while True:
        for ip in get_ipv4_addrs():
            for source, name, path in VARIANTS:
                payload = json.dumps(build_payload(ip, source, name, path)).encode("utf-8")
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((ip, 0))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                sock.sendto(payload, (MCAST_GROUP, MCAST_PORT))
                sock.close()
        time.sleep(10)


if __name__ == "__main__":
    main()
