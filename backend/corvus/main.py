"""Corvus core service entry point: python -m corvus.main"""

import uvicorn

from corvus.api.app import create_app
from corvus.config import HOST, PORT

app = create_app()


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
    server.run()


if __name__ == "__main__":
    run()
