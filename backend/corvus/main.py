"""Corvus core service entry point: python -m corvus.main"""

import uvicorn

from corvus.api.app import create_app
from corvus.config import HOST, PORT

app = create_app()


def run() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    run()
