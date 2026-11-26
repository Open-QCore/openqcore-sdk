"""Server-Sent Events streams (chat and voice)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable, Generic, Iterator, List, Optional, TypeVar

import httpx

from ._errors import StreamError, error_from_response

T = TypeVar("T")

__all__ = ["Stream", "AsyncStream"]


def _parse_line(line: str) -> Optional[str]:
    """Return the data of a ``data:`` line, or None for comments/other fields."""
    if not line or line.startswith(":"):
        return None
    if line.startswith("data:"):
        return line[5:].lstrip()
    return None


class _Decoder(Generic[T]):
    def __init__(self, cast: Callable[[dict], T], *, done_marker: bool, is_final: Callable[[dict], bool]) -> None:
        self._cast = cast
        self._done_marker = done_marker
        self._is_final = is_final
        self.finished = False

    def feed(self, line: str) -> Optional[T]:
        data = _parse_line(line)
        if data is None or data == "":
            return None
        if data == "[DONE]":
            self.finished = True
            return None
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        if self._is_final(obj):
            self.finished = True
        return self._cast(obj)


class Stream(Generic[T]):
    """Iterate events of a streamed response. Use as a context manager or iterate to the end.

    ``for chunk in stream: ...`` — the connection closes when the loop ends,
    when you ``break`` (via ``close()``/context manager) or on error.
    """

    def __init__(
        self,
        response: httpx.Response,
        cast: Callable[[dict], T],
        *,
        done_marker: bool = True,
        is_final: Callable[[dict], bool] = lambda _o: False,
    ) -> None:
        self.response = response
        self._decoder: _Decoder[T] = _Decoder(cast, done_marker=done_marker, is_final=is_final)
        self._consumed = False

    def __iter__(self) -> Iterator[T]:
        if self._consumed:
            raise RuntimeError("This stream was already consumed.")
        self._consumed = True
        try:
            for line in self.response.iter_lines():
                item = self._decoder.feed(line)
                if item is not None:
                    yield item
                if self._decoder.finished and self._decoder._done_marker is False:
                    break
            if not self._decoder.finished:
                raise StreamError("The stream ended before the server finished the response.", request=self.response.request)
        finally:
            self.close()

    def text(self) -> str:
        """Consume the stream and return the concatenated text (chat streams)."""
        parts: List[str] = []
        for item in self:
            content = getattr(item, "content", None)
            if isinstance(content, str):
                parts.append(content)
        return "".join(parts)

    def close(self) -> None:
        self.response.close()

    def __enter__(self) -> "Stream[T]":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def headers(self) -> httpx.Headers:
        return self.response.headers


class AsyncStream(Generic[T]):
    """Async counterpart of :class:`Stream` (``async for chunk in stream``)."""

    def __init__(
        self,
        response: httpx.Response,
        cast: Callable[[dict], T],
        *,
        done_marker: bool = True,
        is_final: Callable[[dict], bool] = lambda _o: False,
    ) -> None:
        self.response = response
        self._decoder: _Decoder[T] = _Decoder(cast, done_marker=done_marker, is_final=is_final)
        self._consumed = False

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[T]:
        if self._consumed:
            raise RuntimeError("This stream was already consumed.")
        self._consumed = True
        try:
            async for line in self.response.aiter_lines():
                item = self._decoder.feed(line)
                if item is not None:
                    yield item
                if self._decoder.finished and self._decoder._done_marker is False:
                    break
            if not self._decoder.finished:
                raise StreamError("The stream ended before the server finished the response.", request=self.response.request)
        finally:
            await self.close()

    async def text(self) -> str:
        parts: List[str] = []
        async for item in self:
            content = getattr(item, "content", None)
            if isinstance(content, str):
                parts.append(content)
        return "".join(parts)

    async def close(self) -> None:
        await self.response.aclose()

    async def __aenter__(self) -> "AsyncStream[T]":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    @property
    def headers(self) -> httpx.Headers:
        return self.response.headers


def raise_for_stream_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        response.read()
        raise error_from_response(response)


async def araise_for_stream_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        await response.aread()
        raise error_from_response(response)
