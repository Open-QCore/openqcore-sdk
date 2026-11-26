"""The OpenQCore clients."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import httpx

from . import _models as m
from ._base import DEFAULT_MAX_RETRIES, AsyncHTTP, SyncHTTP
from ._specs import Spec, auth_login
from ._streaming import AsyncStream, Stream
from .resources import _async as ar
from .resources import _sync as sr

__all__ = ["OpenQCore", "AsyncOpenQCore"]


def _is_voice_final(obj: dict) -> bool:
    return obj.get("type") in ("done", "error")


def _stream_kwargs(spec: Spec) -> dict:
    if spec.cast is m.VoiceEvent:
        return {"done_marker": False, "is_final": _is_voice_final}
    return {}


class OpenQCore(SyncHTTP):
    """Synchronous client.

    >>> from openqcore import OpenQCore
    >>> client = OpenQCore()  # reads OPENQCORE_API_KEY
    >>> session = client.sessions.create(title="Support")
    >>> reply = client.chat.create(session_id=session.id, message="Hello")
    >>> print(reply.content)

    Args:
        api_key: API key (``X-API-Key``). Defaults to ``OPENQCORE_API_KEY``.
        access_token: JWT from ``auth.login`` (``Authorization: Bearer``).
            Defaults to ``OPENQCORE_ACCESS_TOKEN``. Needed to manage API keys.
        base_url: Defaults to ``OPENQCORE_BASE_URL`` or ``https://api.openqcore.com/api/v1``.
        workspace_id: Sent as ``X-Workspace-ID`` on every request
            (defaults to ``OPENQCORE_WORKSPACE_ID``).
        timeout: Seconds or an ``httpx.Timeout``. Default 120 s (10 s to connect).
        max_retries: Retries for 429/503 and network failures. Default 2.
        http_client: Your own ``httpx.Client`` (proxies, transports, …).
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
        timeout: Any = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            access_token=access_token,
            base_url=base_url,
            workspace_id=workspace_id,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.auth = sr.Auth(self)
        self.chat = sr.Chat(self)
        self.sessions = sr.Sessions(self)
        self.messages = sr.Messages(self)
        self.voice = sr.Voice(self)
        self.images = sr.Images(self)
        self.videos = sr.Videos(self)
        self.ocr = sr.OCR(self)
        self.knowledge = sr.Knowledge(self)
        self.archive = sr.Archive(self)
        self.api_keys = sr.ApiKeys(self)
        self.workspace_api_keys = sr.WorkspaceApiKeys(self)
        self.models = sr.Models(self)
        self.usage = sr.Usage(self)
        self.search = sr.Search(self)
        self.rag = sr.Rag(self)
        self.embeddings = sr.Embeddings(self)
        self.ingest = sr.Ingest(self)

    @classmethod
    def from_credentials(cls, *, email: str, password: str, **kwargs: Any) -> "OpenQCore":
        """Sign in with email and password and return a client using the access token."""
        bootstrap = cls(api_key="", access_token="", **kwargs)
        try:
            token = bootstrap._execute(auth_login(email, password))
        finally:
            bootstrap.close()
        return cls(access_token=token.access_token, api_key="", **kwargs)

    def with_options(self, **overrides: Any) -> "OpenQCore":
        """A copy of this client with some settings changed (shares the connection pool)."""
        settings: Dict[str, Any] = dict(
            api_key=self.api_key,
            access_token=self.access_token,
            base_url=self.base_url,
            workspace_id=self.workspace_id,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers=self._default_headers,
            http_client=self._client,
        )
        settings.update(overrides)
        clone = OpenQCore(**settings)
        clone._owns_client = False
        return clone

    def _execute(self, spec: Spec) -> Any:
        response = self.request(spec.opts)
        if spec.kind == "stream":
            return Stream(response, spec.cast, **_stream_kwargs(spec))
        if spec.kind == "bytes":
            return response.content
        if response.status_code == 204 or not response.content:
            return spec.cast({}) if spec.cast is not bytes else b""
        return spec.cast(response.json())

    def __enter__(self) -> "OpenQCore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncOpenQCore(AsyncHTTP):
    """Asynchronous client. Same API as :class:`OpenQCore`, with ``await``.

    >>> client = AsyncOpenQCore()
    >>> session = await client.sessions.create()
    >>> stream = await client.chat.stream(session_id=session.id, message="Hi")
    >>> async for chunk in stream:
    ...     print(chunk.content or "", end="")
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
        timeout: Any = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            access_token=access_token,
            base_url=base_url,
            workspace_id=workspace_id,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.auth = ar.Auth(self)
        self.chat = ar.Chat(self)
        self.sessions = ar.Sessions(self)
        self.messages = ar.Messages(self)
        self.voice = ar.Voice(self)
        self.images = ar.Images(self)
        self.videos = ar.Videos(self)
        self.ocr = ar.OCR(self)
        self.knowledge = ar.Knowledge(self)
        self.archive = ar.Archive(self)
        self.api_keys = ar.ApiKeys(self)
        self.workspace_api_keys = ar.WorkspaceApiKeys(self)
        self.models = ar.Models(self)
        self.usage = ar.Usage(self)
        self.search = ar.Search(self)
        self.rag = ar.Rag(self)
        self.embeddings = ar.Embeddings(self)
        self.ingest = ar.Ingest(self)

    @classmethod
    async def from_credentials(cls, *, email: str, password: str, **kwargs: Any) -> "AsyncOpenQCore":
        bootstrap = cls(api_key="", access_token="", **kwargs)
        try:
            token = await bootstrap._execute(auth_login(email, password))
        finally:
            await bootstrap.close()
        return cls(access_token=token.access_token, api_key="", **kwargs)

    def with_options(self, **overrides: Any) -> "AsyncOpenQCore":
        settings: Dict[str, Any] = dict(
            api_key=self.api_key,
            access_token=self.access_token,
            base_url=self.base_url,
            workspace_id=self.workspace_id,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers=self._default_headers,
            http_client=self._client,
        )
        settings.update(overrides)
        clone = AsyncOpenQCore(**settings)
        clone._owns_client = False
        return clone

    async def _execute(self, spec: Spec) -> Any:
        response = await self.request(spec.opts)
        if spec.kind == "stream":
            return AsyncStream(response, spec.cast, **_stream_kwargs(spec))
        if spec.kind == "bytes":
            return response.content
        if response.status_code == 204 or not response.content:
            return spec.cast({}) if spec.cast is not bytes else b""
        return spec.cast(response.json())

    async def __aenter__(self) -> "AsyncOpenQCore":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
