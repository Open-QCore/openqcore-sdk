"""Synchronous resources.

`_async.py` is GENERATED from this file by ``scripts/gen_async.py`` — edit
here, then run ``python scripts/gen_async.py``. A test fails if they differ.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterable, List, Mapping, Optional, Sequence, Union

from .. import _models as m
from .. import _specs as s
from .._errors import OpenQCoreError
from .._files import FileInput
from .._streaming import Stream

if TYPE_CHECKING:
    from .._client import OpenQCore

__all__ = [
    "Auth",
    "Chat",
    "Sessions",
    "Messages",
    "Voice",
    "Images",
    "Videos",
    "OCR",
    "Knowledge",
    "Archive",
    "ApiKeys",
    "WorkspaceApiKeys",
    "Models",
    "Usage",
    "Search",
    "Rag",
    "Embeddings",
    "Ingest",
]


class _Resource:
    def __init__(self, client: "OpenQCore") -> None:
        self._client = client

    def _run(self, spec: s.Spec) -> Any:
        return self._client._execute(spec)


# ============================================================================ auth


class Auth(_Resource):
    def login(self, *, email: str, password: str) -> m.Token:
        """Exchange email and password for an access token (JWT)."""
        return self._run(s.auth_login(email, password))

    def refresh(self) -> m.Token:
        """Get a fresh access token for the current one (must not be expired)."""
        return self._run(s.auth_refresh())


# ============================================================================ chat


class Chat(_Resource):
    def create(
        self,
        *,
        session_id: str,
        message: Optional[str] = None,
        messages: Optional[Sequence[Mapping[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
        tool_choice: Any = None,
        metadata: Optional[Mapping[str, Any]] = None,
        request_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        scope: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: Any = None,
    ) -> m.ChatCompletion:
        """Send one turn and wait for the full reply.

        The session must exist (``sessions.create``); the server keeps the
        history, so send only the new message.
        """
        return self._run(
            s.chat_completion(
                session_id=session_id, message=message, messages=messages, model=model, stream=False,
                temperature=temperature, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice,
                metadata=metadata, request_id=request_id, workspace_id=workspace_id, scope=scope,
                agent_id=agent_id, timeout=timeout,
            )
        )

    def stream(
        self,
        *,
        session_id: str,
        message: Optional[str] = None,
        messages: Optional[Sequence[Mapping[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
        tool_choice: Any = None,
        metadata: Optional[Mapping[str, Any]] = None,
        request_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        scope: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: Any = None,
    ) -> Stream[m.ChatChunk]:
        """Send one turn and stream the reply as :class:`ChatChunk` events."""
        return self._run(
            s.chat_completion(
                session_id=session_id, message=message, messages=messages, model=model, stream=True,
                temperature=temperature, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice,
                metadata=metadata, request_id=request_id, workspace_id=workspace_id, scope=scope,
                agent_id=agent_id, timeout=timeout,
            )
        )

    def health(self) -> m.Model:
        return self._run(s.chat_health())


# ============================================================================ sessions


class Sessions(_Resource):
    def create(
        self,
        *,
        title: Optional[str] = None,
        folder_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> m.Session:
        return self._run(s.sessions_create(title, folder_id, workspace_id, agent_id))

    def list(
        self,
        *,
        kind: Optional[str] = None,
        agent_id: Optional[str] = None,
        pinned: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> m.SessionList:
        return self._run(s.sessions_list(kind, agent_id, pinned, limit, offset))

    def update(
        self,
        session_id: str,
        *,
        title: Optional[str] = None,
        pinned: Optional[bool] = None,
        starred: Optional[bool] = None,
        marked_unread: Optional[bool] = None,
        folder_id: Optional[str] = None,
    ) -> m.Model:
        return self._run(s.sessions_update(session_id, title, pinned, starred, marked_unread, folder_id))

    def delete(self, session_id: str) -> m.Model:
        return self._run(s.sessions_delete(session_id))

    def messages(self, session_id: str) -> m.MessageList:
        """All messages of a session, oldest first."""
        return self._run(s.sessions_messages(session_id))


class Messages(_Resource):
    def retrieve(self, message_id: str) -> m.Message:
        return self._run(s.messages_retrieve(message_id))

    def update(self, message_id: str, *, content: str, payload: Optional[Mapping[str, Any]] = None) -> m.Model:
        return self._run(s.messages_update(message_id, content, payload))

    def history(self, message_id: str) -> m.Model:
        return self._run(s.messages_history(message_id))

    def undo(self, message_id: str) -> m.Model:
        return self._run(s.messages_undo(message_id))

    def delete(self, message_id: str) -> m.Model:
        return self._run(s.messages_delete(message_id))


# ============================================================================ voice


class Voice(_Resource):
    def stream(self, *, file: FileInput, session_id: str, model: str = "pulse", timeout: Any = None) -> Stream[m.VoiceEvent]:
        """Upload a recording; stream the transcript, the reply text and spoken audio chunks.

        Events: ``user_text``, ``status``, ``text_delta``, ``audio_chunk_ready``,
        then ``done`` (or ``error``).
        """
        return self._run(s.voice_stream(file, session_id, model, timeout))

    def reply_audio(
        self,
        *,
        file: FileInput,
        session_id: str,
        user_text: str,
        response_text: str,
        user_request_id: str,
        assistant_request_id: str,
        model: str = "pulse",
        timeout: Any = None,
    ) -> bytes:
        """The whole reply of a finished voice turn as one MP3 (values come from the ``done`` event)."""
        return self._run(
            s.voice_reply_audio(file, session_id, model, user_text, response_text, user_request_id, assistant_request_id, timeout)
        )

    def speech(self, *, text: str, language: Optional[str] = None) -> bytes:
        """Text to speech (up to 5,000 characters). Returns MP3 bytes."""
        return self._run(s.voice_tts(text, language))

    def interrupt(self, session_id: str) -> m.Model:
        """Stop the reply currently being generated for the session."""
        return self._run(s.voice_interrupt(session_id))


# ============================================================================ iris


def _wait_for_job(get: Any, job_id: str, timeout: float, poll_interval: float) -> m.Job:
    deadline = time.monotonic() + timeout
    while True:
        job = get(job_id)
        if job.is_finished:
            return job
        if time.monotonic() >= deadline:
            raise OpenQCoreError(f"Job {job_id} did not finish within {timeout:.0f}s (last status: {job.status}).")
        time.sleep(poll_interval)


class Images(_Resource):
    def generate(
        self,
        *,
        prompt: str,
        size: Optional[str] = None,
        steps: Optional[int] = None,
        guidance: Optional[float] = None,
        seed: Optional[int] = None,
        num_outputs: Optional[int] = None,
        policy_mode: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: Any = None,
    ) -> m.Job:
        """Generate images. Needs a workspace API key."""
        return self._run(s.images_generate(prompt, size, steps, guidance, seed, num_outputs, policy_mode, provider, timeout))

    def retrieve(self, job_id: str) -> m.Job:
        return self._run(s.images_retrieve(job_id))

    def download(self, job_id: str, *, index: int = 0) -> bytes:
        return self._run(s.images_download(job_id, index))

    def wait(self, job_id: str, *, timeout: float = 300.0, poll_interval: float = 2.0) -> m.Job:
        """Poll until the job is done, failed or blocked."""
        return _wait_for_job(self.retrieve, job_id, timeout, poll_interval)


class Videos(_Resource):
    def generate(
        self,
        *,
        prompt: str,
        length: Optional[int] = None,
        steps: Optional[int] = None,
        target_size: Optional[int] = None,
        cfg: Optional[float] = None,
        image: Optional[str] = None,
        timeout: Any = None,
    ) -> m.Job:
        return self._run(s.videos_generate(prompt, length, steps, target_size, cfg, image, timeout))

    def retrieve(self, job_id: str) -> m.Job:
        return self._run(s.videos_retrieve(job_id))

    def wait(self, job_id: str, *, timeout: float = 900.0, poll_interval: float = 5.0) -> m.Job:
        return _wait_for_job(self.retrieve, job_id, timeout, poll_interval)


class OCR(_Resource):
    def extract(self, *, file: FileInput, timeout: Any = None) -> m.OCRResult:
        """Read a document or ID image: text, document type, structured fields and risk checks."""
        return self._run(s.ocr_extract(file, timeout))


# ============================================================================ knowledge


class Knowledge(_Resource):
    def list(self, *, limit: Optional[int] = None, offset: Optional[int] = None, status: Optional[str] = None) -> m.KnowledgeList:
        return self._run(s.knowledge_list(limit, offset, status))

    def create(
        self,
        *,
        title: str,
        content: str,
        description: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> m.KnowledgeItem:
        """Add plain text (indexed in the background; status starts as ``processing``)."""
        return self._run(s.knowledge_create(title, content, description, tags))

    def upload(
        self,
        *,
        file: FileInput,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Union[str, Sequence[str]]] = None,
        timeout: Any = None,
    ) -> m.KnowledgeItem:
        """Upload a PDF, DOCX, TXT or Markdown file (max 20 MB)."""
        return self._run(s.knowledge_upload(file, title, description, tags, timeout))

    def retrieve(self, knowledge_id: str) -> m.KnowledgeItem:
        return self._run(s.knowledge_retrieve(knowledge_id))

    def update(
        self,
        knowledge_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> m.KnowledgeItem:
        return self._run(s.knowledge_update(knowledge_id, title, description, tags))

    def delete(self, knowledge_id: str) -> m.Model:
        return self._run(s.knowledge_delete(knowledge_id))

    def ask(
        self,
        *,
        question: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        item_ids: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
        model: Optional[str] = None,
        timeout: Any = None,
    ) -> m.KnowledgeAnswer:
        """Answer a question from your processed items, with citations."""
        return self._run(s.knowledge_ask(question, top_k, min_score, item_ids, tags, model, timeout))

    def wait_until_processed(self, knowledge_id: str, *, timeout: float = 300.0, poll_interval: float = 2.0) -> m.KnowledgeItem:
        """Poll until indexing finishes. Raises if it failed."""
        deadline = time.monotonic() + timeout
        while True:
            item = self.retrieve(knowledge_id)
            if item.status == "processed":
                return item
            if item.status == "failed":
                raise OpenQCoreError(f"Indexing failed for {knowledge_id}: {item.error_msg or 'unknown error'}")
            if time.monotonic() >= deadline:
                raise OpenQCoreError(f"{knowledge_id} was not processed within {timeout:.0f}s (status: {item.status}).")
            time.sleep(poll_interval)


# ============================================================================ archive


class Archive(_Resource):
    def create(
        self,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        engine_scope: Optional[str] = None,
        signals: Any = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
        sensitivity: Optional[str] = None,
    ) -> m.ArchiveUnit:
        return self._run(s.archive_create(dict(
            title=title, summary=summary, content=content, category=category, engine_scope=engine_scope,
            signals=signals, confidence=confidence, source=source, sensitivity=sensitivity,
        )))

    def list(
        self,
        *,
        category: Optional[str] = None,
        engine_scope: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> m.ArchiveList:
        return self._run(s.archive_list(category, engine_scope, limit, offset))

    def retrieve(self, unit_id: str) -> m.ArchiveUnit:
        return self._run(s.archive_retrieve(unit_id))

    def update(
        self,
        unit_id: str,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        engine_scope: Optional[str] = None,
        signals: Any = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
        sensitivity: Optional[str] = None,
    ) -> m.ArchiveUnit:
        return self._run(s.archive_update(unit_id, dict(
            title=title, summary=summary, content=content, category=category, engine_scope=engine_scope,
            signals=signals, confidence=confidence, source=source, sensitivity=sensitivity,
        )))

    def delete(self, unit_id: str) -> m.Model:
        return self._run(s.archive_delete(unit_id))


# ============================================================================ api keys


class ApiKeys(_Resource):
    """Personal API keys. Needs a signed-in user (access_token), not an API key."""

    def create(self, *, name: Optional[str] = None) -> m.ApiKey:
        """The full key is only returned here — store it right away."""
        return self._run(s.api_keys_create(name))

    def list(self) -> List[m.ApiKey]:
        return self._run(s.api_keys_list())

    def revoke(self, key_id: int) -> m.Model:
        return self._run(s.api_keys_revoke(key_id))

    def disable(self, key_id: int) -> m.Model:
        return self._run(s.api_keys_disable(key_id))


class WorkspaceApiKeys(_Resource):
    """Workspace API keys. Needs a signed-in workspace admin."""

    def create(
        self,
        workspace_id: str,
        *,
        name: str,
        scopes: Optional[str] = None,
        daily_limit: Optional[int] = None,
        monthly_token_limit: Optional[int] = None,
        is_unlimited: Optional[bool] = None,
    ) -> m.ApiKey:
        return self._run(s.workspace_keys_create(workspace_id, name, scopes, daily_limit, monthly_token_limit, is_unlimited))

    def list(self, workspace_id: str) -> List[m.ApiKey]:
        return self._run(s.workspace_keys_list(workspace_id))

    def delete(self, workspace_id: str, key_id: int) -> m.Model:
        return self._run(s.workspace_keys_delete(workspace_id, key_id))


# ============================================================================ models / usage / retrieval


class Models(_Resource):
    def list(self, *, product_key: Optional[str] = None) -> m.ModelList:
        """Models you can pass as ``model`` (``product_key="chat"`` for chat models only)."""
        return self._run(s.models_list(product_key))


class Usage(_Resource):
    def me(self) -> m.Model:
        """Usage of the API key making the call."""
        return self._run(s.usage_me())


class Search(_Resource):
    def query(self, *, query: str, top_k: Optional[int] = None, source: Optional[str] = None, country: Optional[str] = None) -> m.Model:
        return self._run(s.search_query(query, top_k, source, country))


class Rag(_Resource):
    def ask(
        self,
        *,
        question: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        min_hits: Optional[int] = None,
        country: Optional[str] = None,
        source: Optional[str] = None,
        lang: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Any = None,
    ) -> m.Model:
        return self._run(s.rag_ask(question, top_k, min_score, min_hits, country, source, lang, model, temperature, timeout))


class Embeddings(_Resource):
    def create(self, *, input: Union[str, Sequence[str]], model: Optional[str] = None) -> m.Model:
        return self._run(s.embeddings_create(input if isinstance(input, str) else list(input), model))


class Ingest(_Resource):
    def create(self, *, items: Iterable[Union[str, Mapping[str, Any]]]) -> m.Model:
        """Add text to your private retrieval corpus (used by ``search`` and ``rag``)."""
        return self._run(s.ingest_create(items))
