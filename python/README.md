# OpenQCore Python SDK

[![PyPI](https://img.shields.io/pypi/v/openqcore.svg)](https://pypi.org/project/openqcore/)
[![Python](https://img.shields.io/pypi/pyversions/openqcore.svg)](https://pypi.org/project/openqcore/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

The official Python library for the [OpenQCore API](https://www.openqcore.com/docs): chat with streaming, voice, Iris (image and video generation, document OCR), knowledge bases with cited answers, archive, and API key management.

- Sync **and** async clients with the same API
- Streaming as plain iterators: text, progress status and media
- One typed exception per HTTP status, carrying the server's `code` and `trace_id`
- Automatic, safe retries (429 / 503 / network), timeouts, and idempotent chat requests
- Fully typed (`py.typed`), Python 3.9+, one dependency (`httpx`)

## Installation

```bash
pip install openqcore
```

## Quickstart

Create an API key in the [OpenQCore console](https://www.openqcore.com) and export it:

```bash
export OPENQCORE_API_KEY="oqc_live_..."
```

```python
from openqcore import OpenQCore

client = OpenQCore()  # reads OPENQCORE_API_KEY

session = client.sessions.create(title="Weekly sync")
reply = client.chat.create(
    session_id=session.id,
    message="Summarize the last meeting in three bullet points",
)
print(reply.content)
print(reply.usage.total_tokens)
```

Conversations live in a **session**: create it once and send every turn with the same `session_id`. The server keeps the history, so you only send the new message.

## Streaming

```python
stream = client.chat.stream(session_id=session.id, message="Write a short product update")

for chunk in stream:
    if chunk.status:                      # progress: thinking, searching, ...
        print(f"[{chunk.status.stage}]")
    if chunk.content:                     # the next piece of text
        print(chunk.content, end="", flush=True)
    if chunk.payload:                     # media produced in this turn
        print(chunk.payload.images)
```

Need only the final text? `client.chat.stream(...).text()`.

## Async

```python
import asyncio
from openqcore import AsyncOpenQCore

async def main() -> None:
    async with AsyncOpenQCore() as client:
        session = await client.sessions.create()
        stream = await client.chat.stream(session_id=session.id, message="Hello!")
        async for chunk in stream:
            print(chunk.content or "", end="", flush=True)

asyncio.run(main())
```

Every method of `OpenQCore` exists on `AsyncOpenQCore` with `await`.

## Models

```python
for model in client.models.list(product_key="chat").data:
    print(model.id, "-", model.public_name)

reply = client.chat.create(session_id=session.id, message="Hi", model="pulse")
```

## Voice

```python
stream = client.voice.stream(file="question.webm", session_id=session.id)

for event in stream:
    if event.type == "user_text":
        print("You said:", event.text)
    elif event.type == "text_delta":
        print(event.delta, end="", flush=True)
    elif event.type == "audio_chunk_ready":
        play(event.audio_url)             # spoken reply, sentence by sentence
    elif event.type == "done":
        done = event

# The whole reply as one MP3 (optional)
mp3 = client.voice.reply_audio(
    file="question.webm", session_id=session.id,
    user_text=done.user_text, response_text=done.response_text,
    user_request_id=done.user_request_id, assistant_request_id=done.assistant_request_id,
)

# Text to speech
open("hello.mp3", "wb").write(client.voice.speech(text="Your order has shipped.", language="en"))

# Stop a reply when the user talks over it
client.voice.interrupt(session.id)
```

## Iris: images, video and OCR

```python
# Image generation needs a workspace API key
job = client.images.generate(prompt="Product shot of a ceramic mug", num_outputs=2)
job = client.images.wait(job.job_id)          # no-op if it already finished
png = client.images.download(job.job_id, index=0)

video = client.videos.generate(prompt="Slow aerial shot over a foggy forest")
video = client.videos.wait(video.job_id)
print(video.output_url)

doc = client.ocr.extract(file="passport.jpg")
print(doc.type, doc.confidence, doc.structured_data)
```

Or use an Iris model directly in chat: `client.chat.create(session_id=..., model="iris-genesis", message="A lighthouse at dawn")` — images come back in `reply.payload.images`.

## Knowledge: answers from your own documents

```python
item = client.knowledge.upload(file="handbook.pdf", title="Team Handbook", tags=["hr", "policy"])
client.knowledge.wait_until_processed(item.id)

answer = client.knowledge.ask(question="What is our remote-work policy?", tags=["hr"])
print(answer.answer)
for c in answer.citations:
    print("-", c.title, round(c.score, 2))
```

PDF, DOCX, TXT and Markdown, up to 20 MB. Plain text works too: `client.knowledge.create(title=..., content=...)`.

## Error handling

```python
import openqcore

try:
    client.chat.create(session_id=session.id, message="Hi")
except openqcore.InsufficientBalanceError:
    print("Top up your wallet")
except openqcore.RateLimitError as e:
    print("Retry in", e.retry_after, "seconds")
except openqcore.APIStatusError as e:
    print(e.status_code, e.code, e.message, e.trace_id)
except openqcore.APIConnectionError:
    print("Network problem")
```

| Status | Exception |
| --- | --- |
| 400 | `BadRequestError` |
| 401 | `AuthenticationError` |
| 402 | `InsufficientBalanceError` |
| 403 | `PermissionDeniedError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError` |
| 410 | `GoneError` |
| 413 | `PayloadTooLargeError` |
| 415 | `UnsupportedMediaTypeError` |
| 422 | `UnprocessableEntityError` (`.details` has the field errors) |
| 429 | `RateLimitError` (`.retry_after`) |
| 503 | `ServiceUnavailableError` |
| 504 | `GatewayTimeoutError` |
| other 5xx | `InternalServerError` |

All inherit from `APIStatusError` → `APIError` → `OpenQCoreError`. Include `e.trace_id` when you contact support.

## Retries and timeouts

Requests are retried twice by default, with exponential backoff and the server's `Retry-After`:

- `429` and `503` for every request (the server did not start the work),
- network errors before the request reached the server,
- `5xx` and network errors for reads (`GET`, `DELETE`).

Each chat call carries a generated `request_id`, so a retried turn is never answered twice.

```python
client = OpenQCore(max_retries=5, timeout=60)
client.with_options(timeout=300).knowledge.ask(question="...")   # per call
```

## Authentication

| You have | Use |
| --- | --- |
| An API key (servers, scripts) | `OpenQCore(api_key="oqc_live_...")` or `OPENQCORE_API_KEY` |
| Email and password | `OpenQCore.from_credentials(email=..., password=...)` |
| An access token | `OpenQCore(access_token="eyJ...")` or `OPENQCORE_ACCESS_TOKEN` |

Managing API keys (`client.api_keys`, `client.workspace_api_keys`) needs a signed-in user, not an API key. Keep API keys on your servers; never ship them in browser or mobile apps.

Run requests inside a workspace with `OpenQCore(workspace_id="...")` (sent as `X-Workspace-ID`), or per chat call with `workspace_id=`, `scope=` and `agent_id=`.

## Everything else

| Resource | Methods |
| --- | --- |
| `client.sessions` | `create`, `list`, `update`, `delete`, `messages` |
| `client.messages` | `retrieve`, `update`, `history`, `undo`, `delete` |
| `client.archive` | `create`, `list`, `retrieve`, `update`, `delete` |
| `client.api_keys` | `create`, `list`, `revoke`, `disable` |
| `client.workspace_api_keys` | `create`, `list`, `delete` |
| `client.search` / `client.rag` | `query` / `ask` (API key, private retrieval corpus) |
| `client.ingest` / `client.embeddings` | `create` |
| `client.usage` | `me` |
| `client.auth` | `login`, `refresh` |

Every response is a read-only object with attribute access (`reply.usage.total_tokens`), item access (`reply["content"]`) and `to_dict()`. New fields the API adds are available right away.

## Requirements

Python 3.9 or newer. Configuration via environment: `OPENQCORE_API_KEY`, `OPENQCORE_ACCESS_TOKEN`, `OPENQCORE_BASE_URL`, `OPENQCORE_WORKSPACE_ID`.

## Links

- API documentation: https://www.openqcore.com/docs
- SDK overview: https://www.openqcore.com/developers/sdks
- Support: developers@openqcore.com

MIT licensed.
