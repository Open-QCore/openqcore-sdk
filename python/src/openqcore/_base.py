"""HTTP plumbing shared by the sync and async clients."""

from __future__ import annotations

import os
import platform
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

import httpx

from ._errors import APIConnectionError, APITimeoutError, OpenQCoreError, error_from_response
from ._version import __version__

DEFAULT_BASE_URL = "https://api.openqcore.com/api/v1"
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
DEFAULT_MAX_RETRIES = 2

# 429 and 503 mean the server did not start the work, so any method may be
# retried. 502/504 and network errors are only retried for reads.
_RETRY_ANY = {429, 503}
_RETRY_IDEMPOTENT = {500, 502, 503, 504, 429}
_IDEMPOTENT = {"GET", "HEAD", "OPTIONS", "DELETE"}


@dataclass
class RequestOptions:
    method: str
    path: str
    params: Optional[Mapping[str, Any]] = None
    json: Any = None
    data: Optional[Mapping[str, Any]] = None
    files: Optional[Mapping[str, Tuple[str, bytes, str]]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    auth: bool = True
    stream: bool = False
    timeout: Optional[Any] = None
    max_retries: Optional[int] = None


def _clean(mapping: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if mapping is None:
        return None
    return {k: v for k, v in mapping.items() if v is not None}


class BaseClient:
    def __init__(
        self,
        *,
        api_key: Optional[str],
        access_token: Optional[str],
        base_url: Optional[str],
        workspace_id: Optional[str],
        timeout: Any,
        max_retries: int,
        default_headers: Optional[Mapping[str, str]],
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENQCORE_API_KEY")
        self.access_token = access_token if access_token is not None else os.environ.get("OPENQCORE_ACCESS_TOKEN")
        self.base_url = (base_url or os.environ.get("OPENQCORE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.workspace_id = workspace_id if workspace_id is not None else os.environ.get("OPENQCORE_WORKSPACE_ID")
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self._default_headers = dict(default_headers or {})

    # ------------------------------------------------------------------ headers

    @property
    def user_agent(self) -> str:
        return f"openqcore-python/{__version__} (Python {platform.python_version()}; {platform.system()})"

    def _auth_headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"X-API-Key": self.api_key}
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        raise OpenQCoreError(
            "No credentials. Pass api_key= (or access_token=) to the client, "
            "or set the OPENQCORE_API_KEY environment variable."
        )

    def _build_headers(self, opts: RequestOptions) -> Dict[str, str]:
        headers = {
            "Accept": "text/event-stream" if opts.stream else "application/json",
            "User-Agent": self.user_agent,
            "X-OpenQCore-SDK": f"python/{__version__}",
        }
        if opts.auth:
            headers.update(self._auth_headers())
        if self.workspace_id and "X-Workspace-ID" not in opts.headers:
            headers["X-Workspace-ID"] = str(self.workspace_id)
        headers.update(self._default_headers)
        headers.update({k: v for k, v in opts.headers.items() if v is not None})
        return headers

    def _build_request(self, client: httpx.Client | httpx.AsyncClient, opts: RequestOptions) -> httpx.Request:
        return client.build_request(
            opts.method,
            self.base_url + opts.path,
            params=_clean(opts.params),
            json=opts.json,
            data=_clean(opts.data),
            files=opts.files,
            headers=self._build_headers(opts),
            timeout=opts.timeout if opts.timeout is not None else self.timeout,
        )

    # ------------------------------------------------------------------ retries

    def _retries_for(self, opts: RequestOptions) -> int:
        return self.max_retries if opts.max_retries is None else opts.max_retries

    @staticmethod
    def _should_retry_status(method: str, status: int) -> bool:
        if status in _RETRY_ANY:
            return True
        return method.upper() in _IDEMPOTENT and status in _RETRY_IDEMPOTENT

    @staticmethod
    def _should_retry_error(method: str, exc: Exception) -> bool:
        if isinstance(exc, httpx.ConnectError) or isinstance(exc, httpx.ConnectTimeout):
            return True  # nothing reached the server
        return method.upper() in _IDEMPOTENT and isinstance(exc, (httpx.TransportError,))

    @staticmethod
    def _retry_delay(attempt: int, response: Optional[httpx.Response]) -> float:
        if response is not None:
            header = response.headers.get("retry-after")
            if header:
                try:
                    return min(max(float(header), 0.0), 60.0)
                except ValueError:
                    pass
        base = min(0.5 * (2**attempt), 8.0)
        return base * (0.75 + random.random() * 0.5)

    @staticmethod
    def _wrap_transport_error(exc: Exception, request: Optional[httpx.Request]) -> APIConnectionError:
        if isinstance(exc, httpx.TimeoutException):
            return APITimeoutError(request=request)
        return APIConnectionError(f"Connection error: {exc}", request=request)


class SyncHTTP(BaseClient):
    def __init__(self, *, http_client: Optional[httpx.Client] = None, **kw: Any) -> None:
        super().__init__(**kw)
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(follow_redirects=True)

    def request(self, opts: RequestOptions) -> httpx.Response:
        retries = self._retries_for(opts)
        attempt = 0
        while True:
            request = self._build_request(self._client, opts)
            try:
                response = self._client.send(request, stream=opts.stream)
            except httpx.TransportError as exc:
                if attempt < retries and self._should_retry_error(opts.method, exc):
                    time.sleep(self._retry_delay(attempt, None))
                    attempt += 1
                    continue
                raise self._wrap_transport_error(exc, request) from exc

            if response.status_code < 400:
                return response

            if attempt < retries and self._should_retry_status(opts.method, response.status_code):
                delay = self._retry_delay(attempt, response)
                response.close()
                time.sleep(delay)
                attempt += 1
                continue

            response.read()
            raise error_from_response(response)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class AsyncHTTP(BaseClient):
    def __init__(self, *, http_client: Optional[httpx.AsyncClient] = None, **kw: Any) -> None:
        super().__init__(**kw)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(follow_redirects=True)

    async def request(self, opts: RequestOptions) -> httpx.Response:
        import asyncio

        retries = self._retries_for(opts)
        attempt = 0
        while True:
            request = self._build_request(self._client, opts)
            try:
                response = await self._client.send(request, stream=opts.stream)
            except httpx.TransportError as exc:
                if attempt < retries and self._should_retry_error(opts.method, exc):
                    await asyncio.sleep(self._retry_delay(attempt, None))
                    attempt += 1
                    continue
                raise self._wrap_transport_error(exc, request) from exc

            if response.status_code < 400:
                return response

            if attempt < retries and self._should_retry_status(opts.method, response.status_code):
                delay = self._retry_delay(attempt, response)
                await response.aclose()
                await asyncio.sleep(delay)
                attempt += 1
                continue

            await response.aread()
            raise error_from_response(response)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
