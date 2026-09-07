"""Consistent FastAPI error envelopes without private request values."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException


def register_error_handlers(app: FastAPI):
    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid_structure(request: Request, exc: Exception):
        # Pydantic errors can contain private request values; keep the existing error envelope.
        return JSONResponse(
            {"error": "Invalid structured data; check required fields"}, status_code=400
        )

    @app.exception_handler(ValueError)
    @app.exception_handler(KeyError)
    @app.exception_handler(OSError)
    @app.exception_handler(TypeError)
    async def invalid_operation(request: Request, exc: Exception):
        message = (
            str(exc)
            if request.method == "POST" and isinstance(exc, ValueError)
            else "Invalid request or missing artifact"
        )
        return JSONResponse({"error": message}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers
        )
