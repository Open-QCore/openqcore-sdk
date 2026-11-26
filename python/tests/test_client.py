from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest

import openqcore
from openqcore import (
    AsyncOpenQCore,
    AuthenticationError,
    InsufficientBalanceError,
    NotFoundError,
    OpenQCore,
    OpenQCoreError,
    RateLimitError,
    StreamError,
    UnprocessableEntityError,
    _base,
)

BASE = "https://api.test/api/v1"
SESSION = "2d6c9a51-6f4c-4c43-9c2d-7a3f1c1a9e10"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(_base.time, "sleep", lambda s: None)
    for var in ("OPENQCORE_API_KEY", "OPENQCORE_ACCESS_TOKEN", "OPENQCORE_BASE_URL", "OPENQCORE_WORKSPACE_ID"):
        monkeypatch.delenv(var, raising=False)


class Recorder:
    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self.handler(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def make(handler, **kw) -> "tuple[OpenQCore, Recorder]":
    rec = Recorder(handler)
    kw.setdefault("api_key", "oqc_live_test")
    client = OpenQCore(base_url=BASE, http_client=httpx.Client(transport=httpx.MockTransport(rec)), **kw)
    return client, rec


def envelope(status: int, code: str, message: str, **extra: Any) -> httpx.Response:
    return httpx.Response(
        status,
        json={"success": False, "error": {"code": code, "message": message, "trace_id": "tr-1", "extra": extra}},
    )


def sse(*events: Any) -> httpx.Response:
    lines = []
    for e in events:
        lines.append("data: " + (e if isinstance(e, str) else json.dumps(e)) + "\n\n")
    return httpx.Response(200, content="".join(lines).encode(), headers={"content-type": "text/event-stream"})


def chunk(**delta: Any) -> Dict[str, Any]:
    return {"id": "r1", "choices": [{"delta": delta}]}


# ---------------------------------------------------------------- auth & headers

def test_api_key_header_user_agent_and_workspace():
    client, rec = make(lambda r: httpx.Response(200, json={"status": "ok"}), workspace_id="ws-1")
    client.usage.me()
    h = rec.last.headers
    assert h["x-api-key"] == "oqc_live_test"
    assert "authorization" not in h
    assert h["x-workspace-id"] == "ws-1"
    assert h["user-agent"].startswith(f"openqcore-python/{openqcore.__version__}")
    assert str(rec.last.url) == f"{BASE}/usage/me"


def test_access_token_and_env(monkeypatch):
    monkeypatch.setenv("OPENQCORE_ACCESS_TOKEN", "jwt-1")
    client, rec = make(lambda r: httpx.Response(200, json=[]), api_key=None)
    client.api_keys.list()
    assert rec.last.headers["authorization"] == "Bearer jwt-1"


def test_missing_credentials_is_a_clear_error():
    client, _ = make(lambda r: httpx.Response(200, json={}), api_key=None)
    with pytest.raises(OpenQCoreError, match="OPENQCORE_API_KEY"):
        client.sessions.list()


def test_public_endpoints_need_no_credentials():
    client, rec = make(lambda r: httpx.Response(200, json={"object": "list", "data": [{"id": "pulse"}]}), api_key=None)
    models = client.models.list(product_key="chat")
    assert models.ids == ["pulse"]
    assert rec.last.url.params["product_key"] == "chat"
    assert "x-api-key" not in rec.last.headers


def test_from_credentials_signs_in(monkeypatch):
    monkeypatch.setenv("OPENQCORE_API_KEY", "should-not-be-used")
    seen: List[httpx.Request] = []

    def handler(r):
        seen.append(r)
        if r.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"access_token": "jwt-9", "token_type": "bearer"})
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = OpenQCore.from_credentials(email="a@b.co", password="pw", base_url=BASE, http_client=httpx.Client(transport=transport))
    client.api_keys.list()
    assert json.loads(seen[0].content) == {"email": "a@b.co", "password": "pw"}
    assert "x-api-key" not in seen[0].headers
    assert seen[1].headers["authorization"] == "Bearer jwt-9"


# ---------------------------------------------------------------- chat

def test_chat_create_body_and_response():
    reply = {
        "id": "m1", "message_id": "m1", "content": "Hi!", "session_id": SESSION, "model": "pulse",
        "payload": {"images": [], "files": [], "videos": [], "documents": []},
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "meta": {"trace_id": "t", "request_id": "x", "execution_time_ms": 10, "cached": False},
    }
    client, rec = make(lambda r: httpx.Response(200, json=reply))
    out = client.chat.create(session_id=SESSION, message="Hello", model="pulse", scope="workspace", workspace_id="ws-2")
    body = json.loads(rec.last.content)
    assert body["session_id"] == SESSION and body["message"] == "Hello" and body["stream"] is False
    assert len(body["request_id"]) == 36  # generated so retries are idempotent
    assert "attachments" not in body
    assert rec.last.headers["x-scope-type"] == "workspace" and rec.last.headers["x-workspace-id"] == "ws-2"
    assert out.content == "Hi!" and out.usage.total_tokens == 5 and out["model"] == "pulse"
    assert out.payload.images == [] and out.meta.cached is False
    assert out.to_dict() == reply


def test_chat_requires_a_message():
    client, _ = make(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        client.chat.create(session_id=SESSION)


def test_chat_stream_text_status_and_payload():
    client, rec = make(lambda r: sse(
        chunk(status={"stage": "thinking", "detail": "Thinking"}),
        chunk(content="Hel"),
        ": keep-alive comment",
        chunk(content="lo"),
        chunk(payload={"images": ["https://x/img.png"]}),
        "[DONE]",
    ))
    stream = client.chat.stream(session_id=SESSION, message="hey")
    events = list(stream)
    assert rec.last.headers["accept"] == "text/event-stream"
    assert json.loads(rec.last.content)["stream"] is True
    assert events[0].status.stage == "thinking" and events[0].content is None
    assert "".join(e.content or "" for e in events) == "Hello"
    assert events[-1].payload.images == ["https://x/img.png"]


def test_chat_stream_text_helper():
    client, _ = make(lambda r: sse(chunk(content="a"), chunk(content="b"), "[DONE]"))
    assert client.chat.stream(session_id=SESSION, message="x").text() == "ab"


def test_stream_cut_off_raises():
    client, _ = make(lambda r: sse(chunk(content="partial")))
    with pytest.raises(StreamError):
        list(client.chat.stream(session_id=SESSION, message="x"))


def test_stream_error_status_raises_before_iterating():
    client, _ = make(lambda r: envelope(402, "WALLET_EXHAUSTED", "Balance used up"), max_retries=0)
    with pytest.raises(InsufficientBalanceError) as e:
        client.chat.stream(session_id=SESSION, message="x")
    assert e.value.code == "WALLET_EXHAUSTED"


# ---------------------------------------------------------------- errors & retries

def test_error_envelope_maps_to_typed_exception():
    client, _ = make(lambda r: envelope(404, "SESSION_NOT_FOUND", "Session not found"))
    with pytest.raises(NotFoundError) as e:
        client.sessions.messages(SESSION)
    err = e.value
    assert err.status_code == 404 and err.code == "SESSION_NOT_FOUND" and err.trace_id == "tr-1"
    assert "SESSION_NOT_FOUND" in str(err) and "tr-1" in str(err)


def test_validation_details():
    details = [{"loc": ["body", "session_id"], "msg": "Input should be a valid UUID"}]
    client, _ = make(lambda r: envelope(422, "VALIDATION_ERROR", "Invalid request payload.", details=details))
    with pytest.raises(UnprocessableEntityError) as e:
        client.chat.create(session_id="nope", message="x")
    assert e.value.details == details


def test_plain_detail_bodies_are_understood():
    client, _ = make(lambda r: httpx.Response(401, json={"detail": "Not authenticated"}))
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        client.sessions.list()


def test_429_is_retried_and_then_succeeds():
    calls = iter([
        httpx.Response(429, headers={"retry-after": "1"}, json={"detail": "slow down"}),
        httpx.Response(200, json={"id": SESSION}),
    ])
    client, rec = make(lambda r: next(calls))
    assert client.sessions.create(title="t").id == SESSION
    assert len(rec.requests) == 2


def test_429_after_retries_exposes_retry_after():
    client, rec = make(lambda r: httpx.Response(429, headers={"retry-after": "7"}, json={"detail": "x"}), max_retries=1)
    with pytest.raises(RateLimitError) as e:
        client.sessions.create()
    assert e.value.retry_after == 7.0 and len(rec.requests) == 2


def test_post_is_not_retried_on_500_but_get_is():
    client, rec = make(lambda r: httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(openqcore.InternalServerError):
        client.sessions.create()
    assert len(rec.requests) == 1
    client2, rec2 = make(lambda r: httpx.Response(502, json={"detail": "bad gateway"}))
    with pytest.raises(openqcore.InternalServerError):
        client2.sessions.list()
    assert len(rec2.requests) == 3


def test_connection_error_is_wrapped():
    def boom(r):
        raise httpx.ConnectError("refused", request=r)

    client, rec = make(boom, max_retries=1)
    with pytest.raises(openqcore.APIConnectionError):
        client.sessions.list()
    assert len(rec.requests) == 2


# ---------------------------------------------------------------- sessions / messages

def test_sessions_routes():
    client, rec = make(lambda r: httpx.Response(200, json={"items": [{"id": SESSION}], "total": 1, "limit": 20, "offset": 0}))
    page = client.sessions.list(pinned=True, limit=20)
    assert rec.last.url.params["pinned"] == "true" and page.data[0].id == SESSION
    client.sessions.update(SESSION, title="Renamed")
    assert rec.last.method == "PATCH" and json.loads(rec.last.content) == {"title": "Renamed"}
    with pytest.raises(ValueError):
        client.sessions.update(SESSION)
    client.messages.undo("m1")
    assert rec.last.url.path.endswith("/messages/m1/undo")


# ---------------------------------------------------------------- voice

def test_voice_stream_multipart_and_events(tmp_path: Path):
    audio = tmp_path / "q.webm"
    audio.write_bytes(b"\x1aE\xdf\xa3webm")
    client, rec = make(lambda r: sse(
        {"type": "user_text", "text": "Book a call", "user_request_id": "u1"},
        {"type": "text_delta", "delta": "Sure"},
        {"type": "audio_chunk_ready", "audio_url": "https://x/1.mp3", "text": "Sure"},
        {"type": "done", "response_text": "Sure", "assistant_request_id": "a1"},
    ))
    events = list(client.voice.stream(file=audio, session_id=SESSION))
    assert [e.type for e in events] == ["user_text", "text_delta", "audio_chunk_ready", "done"]
    body = rec.last.content
    assert b'name="session_id"' in body and SESSION.encode() in body and b'name="model"' in body
    assert b"Content-Type: audio/webm" in body


def test_voice_bytes_get_an_audio_type():
    client, rec = make(lambda r: httpx.Response(200, content=b"ID3mp3"))
    out = client.voice.reply_audio(
        file=("rec.bin", b"xx"), session_id=SESSION, user_text="a", response_text="b",
        user_request_id="u", assistant_request_id="a",
    )
    assert out == b"ID3mp3"
    assert b"Content-Type: audio/bin" in rec.last.content


def test_tts_and_interrupt():
    client, rec = make(lambda r: httpx.Response(200, content=b"mp3") if r.url.path.endswith("/tts") else httpx.Response(200, json={"status": "interrupted"}))
    assert client.voice.speech(text="Hi", language="en") == b"mp3"
    assert rec.last.content == b"text=Hi&language=en"
    assert client.voice.interrupt(SESSION).status == "interrupted"
    assert rec.last.content == b""


# ---------------------------------------------------------------- iris

def test_image_job_wait_and_download():
    states = iter(["queued", "running", "done"])

    def handler(r):
        if r.url.path.endswith("/download"):
            return httpx.Response(200, content=b"PNG")
        if r.method == "POST":
            return httpx.Response(200, json={"job_id": "j1", "status": "queued"})
        return httpx.Response(200, json={"job_id": "j1", "status": next(states), "output": ["https://x/1.png"]})

    client, rec = make(handler)
    job = client.images.generate(prompt="mug", size="1024x1024", num_outputs=2)
    assert json.loads(rec.requests[0].content) == {"prompt": "mug", "size": "1024x1024", "num_outputs": 2}
    done = client.images.wait(job.job_id, poll_interval=0)
    assert done.status == "done" and done.outputs == ["https://x/1.png"] and done.is_finished
    assert client.images.download("j1", index=1) == b"PNG" and rec.last.url.params["index"] == "1"


def test_ocr_upload():
    client, rec = make(lambda r: httpx.Response(200, json={"status": "done", "type": "passport", "text": "P<"}))
    out = client.ocr.extract(file=("passport.jpg", b"\xff\xd8jpg"))
    assert out.type == "passport" and b"image/jpeg" in rec.last.content


# ---------------------------------------------------------------- knowledge

def test_knowledge_upload_fields():
    client, rec = make(lambda r: httpx.Response(202, json={"id": "k1", "status": "processing"}))
    item = client.knowledge.upload(file=("handbook.docx", b"PK.."), title="Handbook", tags=["hr", "policy"])
    body = rec.last.content
    assert item.status == "processing"
    assert b'name="tags"\r\n\r\nhr,policy' in body
    assert b"wordprocessingml" in body
    assert b'name="description"' not in body  # None values are not sent


def test_knowledge_wait_until_processed_reports_failure():
    client, _ = make(lambda r: httpx.Response(200, json={"id": "k1", "status": "failed", "error_msg": "Unreadable PDF"}))
    with pytest.raises(OpenQCoreError, match="Unreadable PDF"):
        client.knowledge.wait_until_processed("k1", poll_interval=0)


def test_knowledge_ask_body():
    client, rec = make(lambda r: httpx.Response(200, json={"answer": "3 days [1]", "citations": [{"title": "Handbook"}]}))
    ans = client.knowledge.ask(question="Remote policy?", top_k=3, tags=["hr"])
    assert json.loads(rec.last.content) == {"question": "Remote policy?", "top_k": 3, "tags": ["hr"]}
    assert ans.citations[0].title == "Handbook"


# ---------------------------------------------------------------- keys / archive / retrieval

def test_api_keys_and_workspace_keys():
    client, rec = make(lambda r: httpx.Response(200, json={"items": [{"id": 4, "name": "svc"}], "total": 1}) if "workspaces" in r.url.path else httpx.Response(200, json=[{"id": 3}]))
    assert client.api_keys.list()[0].id == 3
    assert client.workspace_api_keys.list("ws")[0].name == "svc"


def test_archive_and_ingest():
    client, rec = make(lambda r: httpx.Response(200, json={"ok": True}))
    client.archive.create(title="Decision", confidence=0.9)
    assert json.loads(rec.last.content) == {"title": "Decision", "confidence": 0.9}
    client.ingest.create(items=["plain text", {"content": "with meta", "metadata": {"a": 1}}])
    assert json.loads(rec.last.content)["items"][0] == {"content": "plain text"}


def test_models_are_read_only_and_tolerant():
    client, _ = make(lambda r: httpx.Response(200, json={"id": SESSION, "brand_new_field": {"x": 1}}))
    s = client.sessions.create()
    assert s.brand_new_field.x == 1 and s.missing is None
    with pytest.raises(AttributeError):
        s.id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------- async

async def test_async_client_chat_and_stream():
    def handler(r):
        body = json.loads(r.content)
        if body.get("stream"):
            return sse(chunk(content="A"), chunk(content="B"), "[DONE]")
        return httpx.Response(200, json={"content": "sync-ish"})

    client = AsyncOpenQCore(api_key="k", base_url=BASE, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = await client.chat.create(session_id=SESSION, message="x")
    assert out.content == "sync-ish"
    stream = await client.chat.stream(session_id=SESSION, message="x")
    assert await stream.text() == "AB"
    await client.close()


async def test_async_errors():
    client = AsyncOpenQCore(api_key="k", base_url=BASE, max_retries=0,
                            http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: envelope(404, "NOT_FOUND", "nope"))))
    with pytest.raises(NotFoundError):
        await client.knowledge.retrieve("k1")


# ---------------------------------------------------------------- package hygiene

def test_async_resources_are_generated_from_sync():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts" / "gen_async.py"), "--check"], check=False, cwd=root)
    assert result.returncode == 0, "resources/_async.py is stale: run python scripts/gen_async.py"


def test_sync_and_async_expose_the_same_methods():
    from openqcore.resources import _async, _sync

    for name in _sync.__all__:
        s_methods = {k for k in vars(getattr(_sync, name)) if not k.startswith("_")}
        a_methods = {k for k in vars(getattr(_async, name)) if not k.startswith("_")}
        assert s_methods == a_methods, name


def test_fields_named_like_dict_methods_reach_the_data():
    client, _ = make(lambda r: httpx.Response(200, json={"items": [{"id": "k1"}], "total": 1}))
    page = client.knowledge.list()
    assert page.items[0].id == "k1" and page.total == 1 and page.data[0].id == "k1"
    assert "items" in page
