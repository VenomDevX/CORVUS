"""Launch-token authentication for the loopback API.

The Electron main process generates a random token per launch and passes it
to the spawned backend via the CORVUS_TOKEN environment variable. When that
variable is set, every HTTP request and WebSocket handshake must present the
token — otherwise any local process could read conversations or drive the
agent. When it is unset (manual dev backend, tests), nothing is enforced.
"""

import re
import secrets
from urllib.parse import parse_qs

HEADER = b"x-corvus-token"
ADMIN_HEADER = b"x-corvus-admin"
QUERY_PARAM = "token"
# /health stays open so liveness probes never need the token; /handshake is
# open because it proves the *server* knows the token (HMAC of a nonce).
OPEN_PATHS = frozenset({"/health", "/handshake"})
# Consent-bearing routes need a second secret held only by the Electron main
# process, which shows a native dialog first. The renderer's token is not
# enough: script injection in the renderer must not be able to approve
# plugin code or wipe data.
ADMIN_ROUTES = (
    ("POST", re.compile(r"^/plugins/install$")),
    ("POST", re.compile(r"^/plugins/[^/]+/enable$")),
    ("PUT", re.compile(r"^/plugins/[^/]+/permissions$")),
    ("POST", re.compile(r"^/data/wipe$")),
)


def is_admin_route(method: str, path: str) -> bool:
    return any(method == m and rx.match(path) for m, rx in ADMIN_ROUTES)


class TokenAuthMiddleware:
    """Pure ASGI middleware covering both `http` and `websocket` scopes.

    HTTP presents the token in the `X-Corvus-Token` header; WebSockets use
    a `?token=` query parameter because the browser WebSocket API cannot
    set headers. Unauthorized HTTP gets a 401; unauthorized WebSockets are
    closed with code 4401 before the handshake is accepted.
    """

    def __init__(self, app, token: str, admin_token: str | None = None):
        self.app = app
        self.token = token
        self.admin_token = admin_token or secrets.token_hex(32)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        if self._authorized(scope):
            if scope["type"] == "http" and is_admin_route(scope["method"], scope["path"])                     and not self._admin(scope):
                await self._reject(send, 403, b'{"detail":"this action must be approved in Corvus"}')
                return
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Consume the mandatory websocket.connect event, then reject.
            await receive()
            await send({"type": "websocket.close", "code": 4401})
            return
        await self._reject(send, 401, b'{"detail":"missing or invalid Corvus token"}')

    @staticmethod
    async def _reject(send, status: int, body: bytes) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    def _admin(self, scope) -> bool:
        for name, value in scope.get("headers") or []:
            if name == ADMIN_HEADER:
                return secrets.compare_digest(value.decode("latin-1"), self.admin_token)
        return False

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
