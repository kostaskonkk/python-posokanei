"""What the client raises. Everything derives from PosoKaneiError."""

from __future__ import annotations

from typing import Any


class PosoKaneiError(Exception):
    """Base of every error this package raises itself. Network failures stay httpx's."""


class APIError(PosoKaneiError):
    """The API answered with an error status, or with a body that is not JSON."""

    def __init__(self, status_code: int, body: str, message: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"HTTP {status_code}: {body[:200]}")


class NotFoundError(APIError):
    """404: no such product, barcode or path."""


class ForbiddenError(APIError):
    """403. The API refuses a request that does not look like its web app's."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(
            status_code,
            body,
            "HTTP 403: the API refused the request. It wants the web app's headers (Origin, "
            "Referer, X-Platform, X-App-Version) and a browser User-Agent; check `user_agent`, "
            "and any headers of an `http_client` you passed in. It also refuses some networks "
            "whatever the headers.",
        )


class RateLimitError(APIError):
    """429, still, after every retry, or with a wait too long to sit out.

    `retry_after` is the seconds the API asked for, when it said. The barcode endpoint has a
    limit of its own and asks for a quarter of an hour."""

    def __init__(self, status_code: int, body: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        wait = "" if retry_after is None else f" (retry after {retry_after:.0f}s)"
        super().__init__(status_code, body, f"HTTP 429{wait}: {body[:200]}")


class SchemaError(PosoKaneiError):
    """A response did not fit its model. `payload` is what the API sent."""

    def __init__(self, model: str, payload: Any, cause: Exception) -> None:
        self.model = model
        self.payload = payload
        super().__init__(f"the response does not fit {model}: {cause}")
