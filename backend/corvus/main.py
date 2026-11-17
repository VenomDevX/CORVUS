"""Corvus core service entry point: python -m corvus.main"""

import os
import threading

import uvicorn

from corvus.api.app import create_app
from corvus.config import HOST, PORT

app = create_app()


def _exit_with_parent(server: uvicorn.Server) -> None:
    """Stop when the Electron process that spawned us dies, so a crashed app
    never leaves an orphan backend holding a port and the old launch token."""
    raw = os.environ.get("CORVUS_PARENT_PID", "")
    if not raw.isdigit() or os.name != "nt":
        return
    import ctypes

    SYNCHRONIZE, INFINITE = 0x00100000, 0xFFFFFFFF
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(raw))
    if not handle:
        server.should_exit = True  # parent already gone
        return

    def wait() -> None:
        ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
        server.should_exit = True

    threading.Thread(target=wait, name="corvus-parent-watch", daemon=True).start()


def run() -> None:
    # timeout_graceful_shutdown: a lingering connection must never stall the
    # lifespan shutdown (which marks the session clean) indefinitely.
    server = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=PORT, log_level="warning", timeout_graceful_shutdown=3,
    ))
    # POST /shutdown sets server.should_exit for a graceful exit (lifespan
    # shutdown runs). Signals aren't reliable here: native audio libs can
    # replace the C-level SIGINT handler.
    app.state.server = server
    _exit_with_parent(server)
    server.run()


if __name__ == "__main__":
    run()
