"""Session access, response headers and bounded bodies around the FastAPI application."""

import secrets

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 2_000_000
RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
}


class LocalSessionMiddleware:
    def __init__(self, app: ASGIApp, *, origin: str, token: str):
        self.app = app
        self.origin = origin
        self.host = origin.removeprefix("http://")
        self.authorization = ("Bearer " + token).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(RESPONSE_HEADERS)
            await send(message)

        headers = Headers(scope=scope)
        error = None
        if headers.get("host") != self.host:
            error = (403, "Invalid host")
        elif scope["method"] == "POST" and headers.get("origin") != self.origin:
            error = (403, "Same-origin request required")
        elif scope["path"].startswith("/api/") and not secrets.compare_digest(
            headers.get("authorization", "").encode(), self.authorization
        ):
            error = (401, "Open the complete local URL printed by agent-data-workbench ui")
        elif scope["method"] == "POST":
            try:
                length = int(headers["content-length"]) if "content-length" in headers else None
            except ValueError:
                length = -1
            if (
                length is not None
                and not 0 < length <= MAX_BODY_BYTES
                or headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                error = (400, "Supply a JSON body up to 2 MB")
        if error:
            await JSONResponse({"error": error[1]}, status_code=error[0])(
                scope, receive, send_with_headers
            )
            return

        received = 0

        async def receive_bounded():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    raise HTTPException(400, "Supply a JSON body up to 2 MB")
            return message

        await self.app(scope, receive_bounded, send_with_headers)
