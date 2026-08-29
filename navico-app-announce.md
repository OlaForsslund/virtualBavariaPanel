# MFD App Announcer (B&G/Navico)

## Background

The Virtual Bavaria Panel (VBP) webapp can appear on B&G/Navico MFDs as an app tile,
via a proprietary UDP multicast discovery protocol (not avahi/mDNS).

Navico/B&G MFDs listen for JSON "app announcement" broadcasts via UDP multicast to
`239.2.1.1:2053`, sent periodically. VBP includes an announcer script and systemd service
to broadcast the webapp to the MFD automatically.

## Deployment

### Files

- **Script:** `deploy/usr/local/bin/mfd-app-announce.py`
  - Reads the system's global IPv4 address(es) (`ip -o -4 addr show scope global`)
  - Builds the announcement JSON payload
  - Sends it via UDP multicast to `239.2.1.1:2053` (TTL 1, local segment only)
  - Loops forever, re-announcing every 10 seconds (tolerates IP changes)

- **Systemd service:** `deploy/etc/systemd/system/mfd-app-announce.service`
  - Runs the script as root
  - Auto-restarts on failure
  - Starts at boot (`WantedBy=multi-user.target`)
  - Requires lighttpd to be running first

Install:

```bash
sudo cp deploy/etc/systemd/system/mfd-app-announce.service /etc/systemd/system/
sudo cp deploy/usr/local/bin/mfd-app-announce.py /usr/local/bin/
sudo systemctl daemon-reload
sudo systemctl enable --now mfd-app-announce.service
```

### Configuration

Edit the constants at the top of `/usr/local/bin/mfd-app-announce.py`:

```python
APP_PORT = 80
APP_PATH = "/"
APP_NAME = "Bavaria Panel"
APP_DESC = "Virtual Bavaria Panel"
ICON_PATH = "/android-chrome-192x192.png"
SOURCE_ID = "nauticore"
```

Then restart:

```bash
sudo systemctl restart mfd-app-announce
```

- **`APP_NAME` / `APP_DESC`** — shown on the MFD app tile (customize for your boat)
- **`ICON_PATH`** — path to the icon served by VBP's webapp (must exist at that URL)
- **`SOURCE_ID`** — unique identifier for this announcer (useful if running multiple)

## Verification

Join the multicast group temporarily and watch for packets (both Victron's app announcer
and VBP's should appear, one per ~10s):

```python
import socket, struct, time
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', 2053))
mreq = struct.pack("4sl", socket.inet_aton("239.2.1.1"), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
sock.settimeout(2)
end = time.time() + 30
while time.time() < end:
    try:
        data, addr = sock.recvfrom(4096)
        print(addr, data.decode())
    except socket.timeout:
        continue
```

## Useful commands

```bash
sudo systemctl status mfd-app-announce       # check it's running
sudo systemctl restart mfd-app-announce      # after editing the script
sudo journalctl -u mfd-app-announce -f       # tail logs
```

## Requirements & caveats

- Both VBP and the MFD must be on the **same L2 network segment** (same switch/subnet)
  for multicast to reach — no routing between subnets.
- The MFD discovers/loads the app over its wired **Ethernet connection only**
  (WLAN connection from the MFD will not trigger app discovery).
- If VBP's IP changes (new DHCP lease), the announcer picks it up automatically
  on the next 10s cycle — no restart needed.
- The icon must exist and be reachable at `http://<vbp-ip>:80/<ICON_PATH>`.
  The webapp serves icons from its `webapp/` directory (e.g. `webapp/android-chrome-192x192.png`).
