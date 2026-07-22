"""Thread-safe hand-off from the REST/WebSocket server into the main loop.

`GatewayStateMachine` is single-threaded (architecture.md, CLAUDE.md hard
constraints): only `GatewayRuntime.run()`'s thread may call it. Any other
thread that wants to act on the gateway (a REST handler, a WebSocket
handler) must go through `CommandQueue` instead of calling
`GatewayRuntime`/`GatewayStateMachine` directly.

Fire-and-forget: submit() doesn't wait for the command to run, and drain()
doesn't report back per-command. Callers learn the outcome by reading
state back (status snapshot / WebSocket push), same as a physical button
doesn't hand you a receipt.
"""

from __future__ import annotations

import logging
import queue
from typing import Callable

log = logging.getLogger("gateway")


class CommandQueue:
    """Unbounded FIFO. submit() from any thread; drain() from the main loop only."""

    def __init__(self) -> None:
        self._q: queue.Queue[Callable[[], None]] = queue.Queue()

    def submit(self, fn: Callable[[], None]) -> None:
        """Enqueue `fn` to run on the main loop's next drain().

        `fn` takes no arguments — callers close over whatever they need,
        e.g. `queue.submit(lambda: runtime.cmd_set_circuit(mask, True))`.
        Safe to call from any thread other than the main loop's.
        """
        self._q.put(fn)

    def drain(self) -> int:
        """Run every pending command, in submission order. Main loop only.

        Returns the number of commands executed. A command that raises is
        logged and skipped — it must never take down the main loop.
        """
        n = 0
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                return n
            try:
                fn()
            except Exception:
                log.exception("command failed")
            n += 1
