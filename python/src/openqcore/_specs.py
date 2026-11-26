"""One function per endpoint: build the request and say how to read the reply.

The sync and async resources both call these, so the HTTP contract lives
in exactly one place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from . import _models as m
from ._base import RequestOptions
from ._files import FileInput, to_upload

Cast = Callable[[Any], Any]


@dataclass
class Spec:
    opts: RequestOptions
    cast: Cast
    kind: str = "json"  # json | bytes | stream | empty


def _headers(**values: Optional[str]) -> Dict[str, str]:
    names = {"workspace_id": "X-Workspace-ID", "scope": "X-Scope-Type", "agent_id": "X-Agent-ID"}
    return {names[k]: str(v) for k, v in values.items() if v is not None}


def _body(**values: Any) -> Dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _as_list(value: Union[str, Sequence[str], None]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return ",".join(str(v) for v in value)


# ===================================================================== auth

def auth_login(email: str, password: str) -> Spec:
    return Spec(RequestOptions("POST", "/auth/login", json={"email": email, "password": password}, auth=False), m.Token)


def auth_refresh() -> Spec:
    return Spec(RequestOptions("POST", "/auth/refresh"), m.Token)


# ===================================================================== models / usage

def models_list(product_key: Optional[str]) -> Spec:
    return Spec(RequestOptions("GET", "/models/", params={"product_key": product_key}, auth=False), m.ModelList)


def usage_me() -> Spec:
    return Spec(RequestOptions("GET", "/usage/me"), m.Model)


def chat_health() -> Spec:
    return Spec(RequestOptions("GET", "/chat/health", auth=False), m.Model)


# ===================================================================== chat

def chat_completion(
    *,
    session_id: str,
    message: Optional[str],
    messages: Optional[Sequence[Mapping[str, Any]]],
    model: Optional[str],
    stream: bool,
    temperature: Optional[float],
    max_tokens: Optional[int],
    tools: Optional[Sequence[Mapping[str, Any]]],
    tool_choice: Any,
    metadata: Optional[Mapping[str, Any]],
    request_id: Optional[str],
    workspace_id: Optional[str],
    scope: Optional[str],
    agent_id: Optional[str],
    timeout: Any,
) -> Spec:
    if message is None and not messages:
        raise ValueError("Pass message= or messages=.")
    body = _body(
        session_id=str(session_id),
        message=message,
        messages=list(messages) if messages else None,
        model=model,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=list(tools) if tools else None,
        tool_choice=tool_choice,
        metadata=dict(metadata) if metadata else None,
        # A fixed request_id makes retries of this call idempotent on the server.
        request_id=request_id or str(uuid.uuid4()),
    )
    opts = RequestOptions(
        "POST",
        "/chat/completions",
        json=body,
        headers=_headers(workspace_id=workspace_id, scope=scope, agent_id=agent_id),
        stream=stream,
        timeout=timeout,
    )
    if stream:
        return Spec(opts, m.ChatChunk, kind="stream")
    return Spec(opts, m.ChatCompletion)


# ===================================================================== sessions

def sessions_create(title, folder_id, workspace_id, agent_id) -> Spec:
    body = _body(title=title, folder_id=folder_id, workspace_id=workspace_id, agent_id=agent_id)
    return Spec(RequestOptions("POST", "/sessions", json=body), m.Session)


def sessions_list(kind, agent_id, pinned, limit, offset) -> Spec:
    params = {"kind": kind, "agent_id": agent_id, "pinned": None if pinned is None else str(pinned).lower(), "limit": limit, "offset": offset}
    return Spec(RequestOptions("GET", "/sessions", params=params), m.SessionList)


def sessions_update(session_id, title, pinned, starred, marked_unread, folder_id) -> Spec:
    body = _body(title=title, pinned=pinned, starred=starred, marked_unread=marked_unread, folder_id=folder_id)
    if not body:
        raise ValueError("Nothing to update.")
    return Spec(RequestOptions("PATCH", f"/sessions/{session_id}", json=body), m.Model)


def sessions_delete(session_id) -> Spec:
    return Spec(RequestOptions("DELETE", f"/sessions/{session_id}"), m.Model)


def sessions_messages(session_id) -> Spec:
    return Spec(RequestOptions("GET", f"/sessions/{session_id}/messages"), m.MessageList)


# ===================================================================== messages

def messages_retrieve(message_id) -> Spec:
    return Spec(RequestOptions("GET", f"/messages/{message_id}"), m.Message)


def messages_update(message_id, content, payload) -> Spec:
    return Spec(RequestOptions("PATCH", f"/messages/{message_id}", json=_body(content=content, payload=payload)), m.Model)


def messages_history(message_id) -> Spec:
    return Spec(RequestOptions("GET", f"/messages/{message_id}/history"), m.Model)


def messages_undo(message_id) -> Spec:
    return Spec(RequestOptions("POST", f"/messages/{message_id}/undo"), m.Model)


def messages_delete(message_id) -> Spec:
    return Spec(RequestOptions("DELETE", f"/messages/{message_id}"), m.Model)


# ===================================================================== voice

def _audio(file: FileInput) -> Dict[str, Any]:
    return {"file": to_upload(file, default_name="audio.wav", force_type_prefix="audio/")}


def voice_stream(file, session_id, model, timeout) -> Spec:
    opts = RequestOptions(
        "POST",
        "/voice/chat/meta",
        data={"model": model, "session_id": str(session_id)},
        files=_audio(file),
        stream=True,
        timeout=timeout,
    )
    return Spec(opts, m.VoiceEvent, kind="stream")


def voice_reply_audio(file, session_id, model, user_text, response_text, user_request_id, assistant_request_id, timeout) -> Spec:
    data = {
        "model": model,
        "session_id": str(session_id),
        "user_text": user_text,
        "response_text": response_text,
        "user_request_id": user_request_id,
        "assistant_request_id": assistant_request_id,
    }
    return Spec(RequestOptions("POST", "/voice/chat", data=data, files=_audio(file), timeout=timeout), bytes, kind="bytes")


def voice_tts(text, language) -> Spec:
    return Spec(RequestOptions("POST", "/voice/tts", data={"text": text, "language": language}), bytes, kind="bytes")


def voice_interrupt(session_id) -> Spec:
    return Spec(RequestOptions("POST", f"/voice/interrupt/{session_id}"), m.Model)


# ===================================================================== iris

def images_generate(prompt, size, steps, guidance, seed, num_outputs, policy_mode, provider, timeout) -> Spec:
    body = _body(prompt=prompt, size=size, steps=steps, guidance=guidance, seed=seed, num_outputs=num_outputs, policy_mode=policy_mode, provider=provider)
    return Spec(RequestOptions("POST", "/images/generate", json=body, timeout=timeout), m.Job)


def images_retrieve(job_id) -> Spec:
    return Spec(RequestOptions("GET", f"/images/jobs/{job_id}"), m.Job)


def images_download(job_id, index) -> Spec:
    return Spec(RequestOptions("GET", f"/images/jobs/{job_id}/download", params={"index": index}), bytes, kind="bytes")


def videos_generate(prompt, length, steps, target_size, cfg, image, timeout) -> Spec:
    body = _body(prompt=prompt, length=length, steps=steps, target_size=target_size, cfg=cfg, image=image)
    return Spec(RequestOptions("POST", "/videos/generate", json=body, timeout=timeout), m.Job)


def videos_retrieve(job_id) -> Spec:
    return Spec(RequestOptions("GET", f"/videos/jobs/{job_id}"), m.Job)


def ocr_extract(file, timeout) -> Spec:
    return Spec(RequestOptions("POST", "/ocr/generate", files={"file": to_upload(file, default_name="document")}, timeout=timeout), m.OCRResult)


# ===================================================================== knowledge

_K = "/console/knowledge"


def knowledge_list(limit, offset, status) -> Spec:
    return Spec(RequestOptions("GET", _K, params={"limit": limit, "offset": offset, "status": status}), m.KnowledgeList)


def knowledge_create(title, content, description, tags) -> Spec:
    body = _body(title=title, content=content, description=description, tags=list(tags) if tags else None)
    return Spec(RequestOptions("POST", _K, json=body), m.KnowledgeItem)


def knowledge_upload(file, title, description, tags, timeout) -> Spec:
    data = {"title": title, "description": description, "tags": _as_list(tags)}
    return Spec(RequestOptions("POST", f"{_K}/upload", data=data, files={"file": to_upload(file, default_name="document")}, timeout=timeout), m.KnowledgeItem)


def knowledge_retrieve(knowledge_id) -> Spec:
    return Spec(RequestOptions("GET", f"{_K}/{knowledge_id}"), m.KnowledgeItem)


def knowledge_update(knowledge_id, title, description, tags) -> Spec:
    body = _body(title=title, description=description, tags=list(tags) if tags is not None else None)
    if not body:
        raise ValueError("Nothing to update.")
    return Spec(RequestOptions("PATCH", f"{_K}/{knowledge_id}", json=body), m.KnowledgeItem)


def knowledge_delete(knowledge_id) -> Spec:
    return Spec(RequestOptions("DELETE", f"{_K}/{knowledge_id}"), m.Model)


def knowledge_ask(question, top_k, min_score, item_ids, tags, model, timeout) -> Spec:
    body = _body(
        question=question,
        top_k=top_k,
        min_score=min_score,
        item_ids=[str(i) for i in item_ids] if item_ids else None,
        tags=list(tags) if tags else None,
        model=model,
    )
    return Spec(RequestOptions("POST", f"{_K}/ask", json=body, timeout=timeout), m.KnowledgeAnswer)


# ===================================================================== archive

def archive_create(fields: Mapping[str, Any]) -> Spec:
    return Spec(RequestOptions("POST", "/archive/units", json=_body(**fields)), m.ArchiveUnit)


def archive_list(category, engine_scope, limit, offset) -> Spec:
    params = {"category": category, "engine_scope": engine_scope, "limit": limit, "offset": offset}
    return Spec(RequestOptions("GET", "/archive/units", params=params), m.ArchiveList)


def archive_retrieve(unit_id) -> Spec:
    return Spec(RequestOptions("GET", f"/archive/units/{unit_id}"), m.ArchiveUnit)


def archive_update(unit_id, fields: Mapping[str, Any]) -> Spec:
    body = _body(**fields)
    if not body:
        raise ValueError("Nothing to update.")
    return Spec(RequestOptions("PATCH", f"/archive/units/{unit_id}", json=body), m.ArchiveUnit)


def archive_delete(unit_id) -> Spec:
    return Spec(RequestOptions("DELETE", f"/archive/units/{unit_id}"), m.Model)


# ===================================================================== api keys

def api_keys_create(name) -> Spec:
    return Spec(RequestOptions("POST", "/api-keys", json=_body(name=name)), m.ApiKey)


def api_keys_list() -> Spec:
    return Spec(RequestOptions("GET", "/api-keys"), lambda data: [m.ApiKey(i) for i in (data or [])])


def api_keys_revoke(key_id) -> Spec:
    return Spec(RequestOptions("POST", f"/api-keys/{key_id}/revoke"), m.Model)


def api_keys_disable(key_id) -> Spec:
    return Spec(RequestOptions("POST", f"/api-keys/{key_id}/disable"), m.Model)


def workspace_keys_create(workspace_id, name, scopes, daily_limit, monthly_token_limit, is_unlimited) -> Spec:
    body = _body(name=name, scopes=scopes, daily_limit=daily_limit, monthly_token_limit=monthly_token_limit, is_unlimited=is_unlimited)
    return Spec(RequestOptions("POST", f"/workspaces/{workspace_id}/api-keys", json=body), m.ApiKey)


def workspace_keys_list(workspace_id) -> Spec:
    def cast(data: Any) -> List[m.ApiKey]:
        items = data.get("items", data.get("data", [])) if isinstance(data, dict) else data
        return [m.ApiKey(i) for i in (items or [])]

    return Spec(RequestOptions("GET", f"/workspaces/{workspace_id}/api-keys"), cast)


def workspace_keys_delete(workspace_id, key_id) -> Spec:
    return Spec(RequestOptions("DELETE", f"/workspaces/{workspace_id}/api-keys/{key_id}"), m.Model)


# ===================================================================== retrieval

def search_query(query, top_k, source, country) -> Spec:
    return Spec(RequestOptions("POST", "/search", json=_body(query=query, top_k=top_k, source=source, country=country)), m.Model)


def rag_ask(question, top_k, min_score, min_hits, country, source, lang, model, temperature, timeout) -> Spec:
    body = _body(question=question, top_k=top_k, min_score=min_score, min_hits=min_hits, country=country, source=source, lang=lang, model=model, temperature=temperature)
    return Spec(RequestOptions("POST", "/rag/ask", json=body, timeout=timeout), m.Model)


def embeddings_create(input, model) -> Spec:
    return Spec(RequestOptions("POST", "/embeddings", json=_body(input=input, model=model)), m.Model)


def ingest_create(items: Iterable[Union[str, Mapping[str, Any]]]) -> Spec:
    norm = [{"content": i} if isinstance(i, str) else dict(i) for i in items]
    if not norm:
        raise ValueError("items must not be empty.")
    return Spec(RequestOptions("POST", "/ingest", json={"items": norm}), m.Model)
