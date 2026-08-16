"""Small ASGI authentication boundaries for Hublet."""

from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Require one exact bearer token for the wrapped ASGI application."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.authorization = f"Bearer {token}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("authorization", "")
        if not hmac.compare_digest(supplied, self.authorization):
            response = PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class SameOriginMiddleware:
    """Reject dashboard POSTs that did not come from Hublet's own origin."""

    def __init__(self, app: ASGIApp, origin: str) -> None:
        self.app = app
        self.origin = origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and not _is_mcp_path(scope["path"])
            and _request_origin(Headers(scope=scope)) != self.origin
        ):
            await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
            return

        await self.app(scope, receive, send)


class DashboardAuthMiddleware:
    """Redirect private dashboard pages until the signed session is present."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_public_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        session = scope.get("session", {})
        if session.get("authenticated") is not True:
            await RedirectResponse("/login", status_code=303)(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _is_public_path(path: str) -> bool:
    return path in {"/healthz", "/login"} or path.startswith("/static/") or _is_mcp_path(path)


def _is_mcp_path(path: str) -> bool:
    return path == "/mcp" or path.startswith("/mcp/")


def _request_origin(headers: Headers) -> str | None:
    if origin := headers.get("origin"):
        return origin
    if referer := headers.get("referer"):
        parsed = urlsplit(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None
