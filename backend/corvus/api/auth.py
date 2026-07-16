"""Launch-token authentication for the loopback API.

The Electron main process generates a random token per launch and passes it
to the spawned backend via the CORVUS_TOKEN environment variable. When that
variable is set, every HTTP request and WebSocket handshake must present the
token — otherwise any local process could read conversations or drive the
agent. When it is unset (manual dev backend, tests), nothing is enforced.
"""

import secrets
from urllib.parse import parse_qs

HEADER = b"x-corvus-token"
QUERY_PARAM = "token"
# /health stays open so liveness probes (launcher, renderer poll) never
# need the token.
OPEN_PATHS = frozenset({"/health"})


class TokenAuthMiddleware:
    """Pure ASGI middleware covering both `http` and `websocket` scopes.

    HTTP presents the token in the `X-Corvus-Token` header; WebSockets use
    a `?token=` query parameter because the browser WebSocket API cannot
    set headers. Unauthorized HTTP gets a 401; unauthorized WebSockets are
    closed with code 4401 before the handshake is accepted.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        if self._authorized(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Consume the mandatory websocket.connect event, then reject.
            await receive()
            await send({"type": "websocket.close", "code": 4401})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"missing or invalid Corvus token"}',
            }
        )

    def _authorized(self, scope) -> bool:
        supplied = ""
        for name, value in scope.get("headers") or []:
            if name == HEADER:
                supplied = value.decode("latin-1")
                break
        if not supplied:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            values = query.get(QUERY_PARAM)
            if values:
                supplied = values[0]
        return bool(supplied) and secrets.compare_digest(supplied, self.token)
