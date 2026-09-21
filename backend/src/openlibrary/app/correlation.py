"""Request-correlation boundary for HTTP responses and logs."""

import re
from uuid import uuid4

from flask import Flask, Response, g, request


REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


def install_request_correlation(app: Flask) -> None:
    """Use a safe client correlation id or create one before request handling."""

    @app.before_request
    def select_request_id() -> None:
        candidate = request.headers.get(REQUEST_ID_HEADER, "")
        g.request_id = (
            candidate if _VALID_REQUEST_ID.fullmatch(candidate) else str(uuid4())
        )

    @app.after_request
    def add_request_id(response: Response) -> Response:
        response.headers[REQUEST_ID_HEADER] = request_id()
        return response


def request_id() -> str:
    """Return the request identifier selected at the HTTP trust boundary."""
    selected = getattr(g, "request_id", None)
    if isinstance(selected, str):
        return selected

    generated = str(uuid4())
    g.request_id = generated
    return generated
