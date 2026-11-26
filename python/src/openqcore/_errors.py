"""Exceptions raised by the OpenQCore client.

Every error response from the API uses one envelope::

    {"success": false, "error": {"code": "...", "message": "...", "trace_id": "...", "extra": {...}}}

:class:`APIStatusError` exposes those fields, and a subclass is chosen from
the HTTP status so callers can catch exactly what they care about.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

__all__ = [
    "OpenQCoreError",
    "APIError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "BadRequestError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "PayloadTooLargeError",
    "UnsupportedMediaTypeError",
    "UnprocessableEntityError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "GatewayTimeoutError",
    "StreamError",
]


class OpenQCoreError(Exception):
    """Base class for every error raised by this package."""


class APIError(OpenQCoreError):
    """An error that happened while talking to the API."""

    def __init__(self, message: str, *, request: Optional[httpx.Request] = None) -> None:
        super().__init__(message)
        self.message = message
        self.request = request


class APIConnectionError(APIError):
    """The request never got an HTTP response (DNS, TLS, refused, reset…)."""

    def __init__(self, message: str = "Connection error.", *, request: Optional[httpx.Request] = None) -> None:
        super().__init__(message, request=request)


class APITimeoutError(APIConnectionError):
    """The request timed out on the client side."""

    def __init__(self, request: Optional[httpx.Request] = None) -> None:
        super().__init__("Request timed out.", request=request)


class StreamError(APIError):
    """A stream ended before the server sent its final event."""


class APIStatusError(APIError):
    """The API answered with a 4xx or 5xx status."""

    status_code: int

    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response,
        code: Optional[str] = None,
        trace_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message, request=response.request)
        self.response = response
        self.status_code = response.status_code
        self.code = code
        self.trace_id = trace_id
        self.extra = extra or {}
        self.body = body

    def __str__(self) -> str:
        parts = [f"{self.status_code}"]
        if self.code:
            parts.append(self.code)
        parts.append(self.message)
        text = " ".join(parts)
        if self.trace_id:
            text += f" (trace_id={self.trace_id})"
        return text


class BadRequestError(APIStatusError):
    """400: the request is malformed or refers to something invalid."""


class AuthenticationError(APIStatusError):
    """401: missing, expired or invalid credentials."""


class InsufficientBalanceError(APIStatusError):
    """402: wallet balance or free quota is used up (WALLET_EXHAUSTED)."""


class PermissionDeniedError(APIStatusError):
    """403: authenticated, but not allowed (role, workspace, disabled account)."""


class NotFoundError(APIStatusError):
    """404: the resource does not exist or does not belong to you."""


class ConflictError(APIStatusError):
    """409: the same request is already running, or request_id was reused."""


class GoneError(APIStatusError):
    """410: the resource was deleted (for example a chat session)."""


class PayloadTooLargeError(APIStatusError):
    """413: the uploaded file is larger than the endpoint allows."""


class UnsupportedMediaTypeError(APIStatusError):
    """415: the uploaded file type is not supported."""


class UnprocessableEntityError(APIStatusError):
    """422: validation failed. Field errors are in ``extra["details"]``."""

    @property
    def details(self) -> Any:
        return self.extra.get("details")


class RateLimitError(APIStatusError):
    """429: too many requests. ``retry_after`` is in seconds when the server sent it."""

    @property
    def retry_after(self) -> Optional[float]:
        value = self.response.headers.get("retry-after")
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None


class InternalServerError(APIStatusError):
    """5xx: something failed on the server."""


class ServiceUnavailableError(InternalServerError):
    """503: overloaded or a provider is unavailable. Safe to retry later."""


class GatewayTimeoutError(InternalServerError):
    """504: the model did not answer in time."""


_STATUS_MAP = {
    400: BadRequestError,
    401: AuthenticationError,
    402: InsufficientBalanceError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    410: GoneError,
    413: PayloadTooLargeError,
    415: UnsupportedMediaTypeError,
    422: UnprocessableEntityError,
    429: RateLimitError,
    503: ServiceUnavailableError,
    504: GatewayTimeoutError,
}


def error_from_response(response: httpx.Response, body: Any = None) -> APIStatusError:
    """Build the right exception from an error response (body already read)."""
    if body is None:
        try:
            body = response.json()
        except Exception:
            body = response.text or None

    code: Optional[str] = None
    message: Optional[str] = None
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = {}

    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message")
            trace_id = err.get("trace_id")
            extra = err.get("extra") or {}
        elif "detail" in body:
            detail = body["detail"]
            if isinstance(detail, dict):
                code = detail.get("code")
                message = detail.get("message") or detail.get("detail")
            elif isinstance(detail, str):
                message = detail
            else:
                extra = {"details": detail}
    elif isinstance(body, str) and body.strip():
        message = body.strip()[:500]

    trace_id = trace_id or response.headers.get("x-trace-id") or response.headers.get("x-request-id")
    message = message or response.reason_phrase or "Request failed."

    status = response.status_code
    cls = _STATUS_MAP.get(status)
    if cls is None:
        cls = InternalServerError if status >= 500 else APIStatusError
    return cls(message, response=response, code=code, trace_id=trace_id, extra=extra, body=body)
