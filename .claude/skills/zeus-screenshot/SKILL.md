---
name: zeus-screenshot
description: Grab and view a screenshot of the boat's Zeus3 plotter screen (e.g. to check the Bavaria Panel tile or webapp on the real MFD). Needs the plotter powered on.
---

Read-only: `screenshot.sh` pulls one frame from the plotter's RTSP screen mirror and sends no input.

```bash
ssh ola@nauticore 'cd ~/hermes-plotter-remote && timeout 30 ./screenshot.sh /tmp/zeus-grab.png'
scp -q ola@nauticore:/tmp/zeus-grab.png "$SCRATCHPAD/zeus-grab.png" && ssh ola@nauticore 'rm -f /tmp/zeus-grab.png'
```

Then Read the PNG (1024x600). If ffmpeg fails or times out, the plotter is probably off; tell the user, don't retry in a loop.

The script and the plotter IP (default 192.168.2.2) belong to the separate `hermes-plotter-remote` repo on the Pi.
