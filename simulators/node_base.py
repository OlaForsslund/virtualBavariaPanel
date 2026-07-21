"""Shared bus plumbing for the simulators.

Reproduces the real nodes' wire behavior (protocol_findings.md): boot-id
frame + one-shot NMT boot-up, periodic TPDO streaming with alternating
alive toggle, and a minimal expedited-only SDO server (all objects on
this bus fit in 4 bytes).
"""

import time

import can


class SdoAbort(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"SDO abort 0x{code:08X}")
        self.code = code


ABORT_NO_OBJECT = 0x06020000
ABORT_READ_ONLY = 0x06010002
ABORT_BAD_COMMAND = 0x05040001

_DOWNLOAD_SIZES = {0x23: 4, 0x2B: 2, 0x2F: 1}


class SimNode:
    """Subclasses override: boot_ident, tpdo_cob, stream_payload,
    on_frame, sdo_read (returns <=4 bytes), sdo_write."""

    def __init__(self, bus: can.BusABC, node_id: int, stream_period: float) -> None:
        self.bus = bus
        self.node_id = node_id
        self.stream_period = stream_period

    def send(self, cob: int, data: bytes) -> None:
        self.bus.send(can.Message(arbitration_id=cob, data=data, is_extended_id=False))

    def run(self) -> None:
        self.send(0x480 + self.node_id, self.boot_ident())  # boot id/version
        self.send(0x700 + self.node_id, b"\x00")  # one-shot NMT boot-up
        self.started(time.monotonic())
        toggle = False
        next_tx = time.monotonic()
        while True:
            msg = self.bus.recv(timeout=max(0.0, next_tx - time.monotonic()))
            now = time.monotonic()
            if msg is not None and not msg.is_error_frame:
                self.on_message(msg, now)
            if now >= next_tx:
                self.send(self.tpdo_cob(), self.stream_payload(toggle, now))
                toggle = not toggle
                next_tx += self.stream_period
                if next_tx < now:  # fell behind; don't burst-catch-up
                    next_tx = now + self.stream_period

    def started(self, now: float) -> None:
        pass

    def on_message(self, msg: can.Message, now: float) -> None:
        if msg.arbitration_id == 0x600 + self.node_id and len(msg.data) == 8:
            self._handle_sdo(bytes(msg.data))
        else:
            self.on_frame(msg, now)

    # -- expedited SDO server ---------------------------------------------

    def _handle_sdo(self, req: bytes) -> None:
        command = req[0]
        index = req[1] | (req[2] << 8)
        sub = req[3]
        try:
            if command == 0x40:  # upload (read)
                data = self.sdo_read(index, sub)
                unused = 4 - len(data)
                header = 0x43 | (unused << 2)  # expedited, size indicated
                response = bytes([header]) + req[1:4] + data + bytes(unused)
            elif command in _DOWNLOAD_SIZES:  # expedited download (write)
                size = _DOWNLOAD_SIZES[command]
                self.sdo_write(index, sub, req[4 : 4 + size])
                response = bytes([0x60]) + req[1:4] + bytes(4)
            else:
                raise SdoAbort(ABORT_BAD_COMMAND)
        except SdoAbort as abort:
            response = bytes([0x80]) + req[1:4] + abort.code.to_bytes(4, "little")
        self.send(0x580 + self.node_id, response)
