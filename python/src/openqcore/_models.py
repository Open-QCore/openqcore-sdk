"""Response objects.

Responses are thin, read-only wrappers around the JSON the API returned:
attributes work (``completion.content``), item access works
(``completion["content"]``), and ``to_dict()`` gives the raw data back.
Fields the server adds later are available immediately without an SDK
upgrade; the annotations below exist for editors and type checkers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "Model",
    "ChatCompletion",
    "ChatChunk",
    "Usage",
    "Payload",
    "Session",
    "SessionList",
    "Message",
    "MessageList",
    "Job",
    "OCRResult",
    "KnowledgeItem",
    "KnowledgeList",
    "KnowledgeAnswer",
    "ArchiveUnit",
    "ArchiveList",
    "ApiKey",
    "Token",
    "VoiceEvent",
    "ModelInfo",
    "ModelList",
]


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return Model(value)
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


class Model:
    """Read-only view over a JSON object with attribute access.

    Not a ``dict`` subclass on purpose: API fields called ``items``, ``keys``
    or ``values`` must reach the data, not dict methods.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        object.__setattr__(self, "_data", dict(data or {}))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        data = object.__getattribute__(self, "_data")
        if name in data:
            return _wrap(data[name])
        return None

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("OpenQCore response objects are read-only; use to_dict() for a copy.")

    def __getitem__(self, key: str) -> Any:
        return _wrap(self._data[key])

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Model):
            return self._data == other._data
        if isinstance(other, dict):
            return self._data == other
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._data!r})"

    def to_dict(self) -> Dict[str, Any]:
        """A deep copy of the raw JSON."""
        import copy

        return copy.deepcopy(self._data)


class Usage(Model):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Payload(Model):
    images: List[str]
    files: List[Any]
    videos: List[Any]
    documents: List[Any]


class ChatCompletion(Model):
    """Response of ``chat.create`` (non-streaming)."""

    id: str
    message_id: str
    content: str
    session_id: str
    model: str
    payload: Payload
    usage: Usage
    meta: Model


class ChatChunk(Model):
    """One server-sent event of a streamed chat turn.

    ``content`` is the next piece of text, ``status`` a progress update
    (``{"stage": "thinking" | "searching" | ..., "detail": "..."}``) and
    ``payload`` media produced during the turn. Each is ``None`` when the
    chunk does not carry it.
    """

    id: str

    @property
    def delta(self) -> Model:
        choices = self._data.get("choices") or [{}]
        first = choices[0] if isinstance(choices[0], dict) else {}
        delta = first.get("delta") or {}
        return Model(delta if isinstance(delta, dict) else {})

    @property
    def content(self) -> Optional[str]:  # type: ignore[override]
        value = self.delta.to_dict().get("content")
        return value if isinstance(value, str) and value else None

    @property
    def status(self) -> Optional[Model]:  # type: ignore[override]
        value = self.delta.to_dict().get("status")
        return Model(value) if isinstance(value, dict) else None

    @property
    def payload(self) -> Optional[Payload]:  # type: ignore[override]
        value = self.delta.to_dict().get("payload")
        return Payload(value) if isinstance(value, dict) and value else None


class Session(Model):
    id: str
    kind: str
    title: Optional[str]
    workspace_id: Optional[str]
    agent_id: Optional[str]
    pinned: bool
    starred: bool
    created_at: str
    updated_at: str


class SessionList(Model):
    items: List[Session]
    total: int
    limit: int
    offset: int

    @property
    def data(self) -> List[Session]:
        return [Session(i) for i in self._data.get("items") or []]


class Message(Model):
    id: str
    role: str
    content: Any
    payload: Optional[Payload]
    created_at: str


class MessageList(Model):
    items: List[Message]
    total: int

    @property
    def data(self) -> List[Message]:
        return [Message(i) for i in self._data.get("items") or []]


class Job(Model):
    """An Iris image or video job."""

    job_id: str
    status: str  # queued | running | done | failed | blocked
    output_url: Optional[str]
    output: Any
    error: Optional[str]

    @property
    def is_finished(self) -> bool:
        return self._data.get("status") in ("done", "failed", "blocked")

    @property
    def outputs(self) -> List[str]:
        out = self._data.get("output")
        if isinstance(out, list):
            return [o for o in out if isinstance(o, str)]
        url = self._data.get("output_url")
        return [url] if isinstance(url, str) and url else []


class OCRResult(Model):
    job_id: str
    status: str
    type: str
    text: str
    pages: int
    confidence: float
    structured_data: Model
    risk_score: float
    risk_level: str


class KnowledgeItem(Model):
    id: str
    title: str
    description: Optional[str]
    status: str  # processing | processed | failed
    kind: str
    tags: List[str]
    chunks: int
    tokens: int
    file_size: Optional[int]
    error_msg: Optional[str]
    created_at: str


class KnowledgeList(Model):
    items: List[KnowledgeItem]
    total: int

    @property
    def data(self) -> List[KnowledgeItem]:
        return [KnowledgeItem(i) for i in self._data.get("items") or []]


class KnowledgeAnswer(Model):
    answer: str
    citations: List[Model]
    usage: Usage
    metadata: Model


class ArchiveUnit(Model):
    id: str
    owner_type: str
    owner_id: str
    title: Optional[str]
    summary: Optional[str]
    content: Optional[str]
    category: Optional[str]
    engine_scope: Optional[str]
    signals: Any
    confidence: Optional[float]
    source: Optional[str]
    sensitivity: Optional[str]
    created_at: str


class ArchiveList(Model):
    data: List[ArchiveUnit]  # type: ignore[assignment]
    total_count: int
    limit: int
    offset: int


class ApiKey(Model):
    id: int
    key: Optional[str]  # only present in the create response
    name: Optional[str]
    active: bool
    revoked: bool
    created_at: str


class Token(Model):
    access_token: str
    token_type: str


class VoiceEvent(Model):
    """One event of a streamed voice turn (``type`` tells which)."""

    type: str  # user_text | status | text_delta | audio_chunk_ready | done | error


class ModelInfo(Model):
    """One entry of ``models.list()``. Pass ``id`` as ``model`` to the chat API."""

    id: str
    public_name: str
    product_key: str
    type: str
    description: Optional[str]
    context_window: Optional[int]
    generation: Model


class ModelList(Model):
    object: str
    data: List[ModelInfo]  # type: ignore[assignment]

    @property
    def ids(self) -> List[str]:
        return [str(m.get("id")) for m in self._data.get("data") or [] if isinstance(m, dict)]
