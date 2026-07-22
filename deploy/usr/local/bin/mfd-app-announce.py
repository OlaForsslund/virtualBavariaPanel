#!/usr/bin/env python3
import json
import socket
import subprocess
import time

MCAST_GROUP = "239.2.1.1"
MCAST_PORT = 2053
APP_PORT = 80
APP_PATH = "/"
APP_NAME = "Bavaria Panel"
APP_DESC = "Virtual Bavaria Panel"
ICON_PATH = "/favicon-32x32.png"
SOURCE_ID = "olaspi"


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


def build_payload(ip):
    return {
        "Source": SOURCE_ID,
        "IP": ip,
        "Text": [{
            "Language": "en",
            "Name": APP_NAME,
            "Description": APP_DESC,
        }],
        "Icon": f"http://{ip}:{APP_PORT}{ICON_PATH}",
        "URL": f"http://{ip}:{APP_PORT}{APP_PATH}",
        "OnlyShowOnClientIP": "false",
        "BrowserPanel": {
            "Enable": True,
            "ProgressBarEnable": False,
            "MenuText": [{
                "Language": "en",
                "Name": "Home",
            }],
        },
    }


def main():
    while True:
        for ip in get_ipv4_addrs():
            payload = json.dumps(build_payload(ip)).encode("utf-8")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((ip, 0))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.sendto(payload, (MCAST_GROUP, MCAST_PORT))
            sock.close()
        time.sleep(10)


if __name__ == "__main__":
    main()
