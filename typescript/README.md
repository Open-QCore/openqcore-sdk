# OpenQCore TypeScript / JavaScript SDK

[![npm](https://img.shields.io/npm/v/openqcore.svg)](https://www.npmjs.com/package/openqcore)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

The official TypeScript and JavaScript library for the [OpenQCore API](https://www.openqcore.com/docs): chat with streaming, voice, Iris (image and video generation, document OCR), knowledge bases with cited answers, archive, and API key management.

- Full TypeScript types, ESM and CommonJS
- Zero runtime dependencies (built on `fetch`): Node.js 18+, Bun, Deno, Cloudflare Workers, Vercel Edge
- Streaming with `for await`: text, progress status and media
- One typed error class per HTTP status, carrying the server's `code` and `traceId`
- Automatic, safe retries (429 / 503 / network), timeouts, `AbortSignal`, idempotent chat requests

## Installation

```bash
npm install openqcore
# or: pnpm add openqcore · yarn add openqcore · bun add openqcore
```

## Quickstart

Create an API key in the [OpenQCore console](https://www.openqcore.com) and set `OPENQCORE_API_KEY`.

```ts
import OpenQCore from "openqcore";

const client = new OpenQCore(); // reads process.env.OPENQCORE_API_KEY

const session = await client.sessions.create({ title: "Weekly sync" });
const reply = await client.chat.create({
  session_id: session.id,
  message: "Summarize the last meeting in three bullet points",
});

console.log(reply.content);
console.log(reply.usage.total_tokens);
```

Conversations live in a **session**: create it once and send every turn with the same `session_id`. The server keeps the history, so you only send the new message.

## Streaming

```ts
const stream = await client.chat.stream({ session_id: session.id, message: "Write a short product update" });

for await (const chunk of stream) {
  if (chunk.status) console.log(`[${chunk.status.stage}]`); // thinking, searching, ...
  if (chunk.content) process.stdout.write(chunk.content);   // the next piece of text
  if (chunk.payload) console.log(chunk.payload.images);      // media produced in this turn
}
```

Only need the final text? `await (await client.chat.stream({...})).text()`. Stop early with `break` or `stream.abort()`.

### Streaming to a browser (Next.js route handler)

```ts
// app/api/chat/route.ts — the API key stays on the server
import OpenQCore from "openqcore";

const client = new OpenQCore();

export async function POST(req: Request) {
  const { sessionId, message } = await req.json();
  const stream = await client.chat.stream({ session_id: sessionId, message });

  const body = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();
      for await (const chunk of stream) if (chunk.content) controller.enqueue(enc.encode(chunk.content));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
```

## Models

```ts
const { data } = await client.models.list({ product_key: "chat" });
for (const m of data) console.log(m.id, "-", m.public_name);

await client.chat.create({ session_id: session.id, message: "Hi", model: "pulse" });
```

## Voice

```ts
import { readFile, writeFile } from "node:fs/promises";

const stream = await client.voice.stream({ file: "question.webm", session_id: session.id });
let done;
for await (const event of stream) {
  if (event.type === "user_text") console.log("You said:", event.text);
  if (event.type === "text_delta") process.stdout.write(event.delta);
  if (event.type === "audio_chunk_ready") play(event.audio_url); // spoken reply, sentence by sentence
  if (event.type === "done") done = event;
}

// Text to speech
await writeFile("hello.mp3", await client.voice.speech({ text: "Your order has shipped.", language: "en" }));

// Stop a reply when the user talks over it
await client.voice.interrupt(session.id);
```

Files can be a path (Node.js), a `Blob`/`File`, bytes, or `{ data, filename, contentType }`. In the browser, record with `MediaRecorder` and pass the resulting `Blob` — from your own backend, so your API key is never exposed.

## Iris: images, video and OCR

```ts
// Image generation needs a workspace API key
let job = await client.images.generate({ prompt: "Product shot of a ceramic mug", num_outputs: 2 });
job = await client.images.wait(job.job_id);
const png = await client.images.download(job.job_id, { index: 0 });

let video = await client.videos.generate({ prompt: "Slow aerial shot over a foggy forest" });
video = await client.videos.wait(video.job_id);
console.log(video.output_url);

const doc = await client.ocr.extract({ file: "passport.jpg" });
console.log(doc.type, doc.confidence, doc.structured_data);
```

Or use an Iris model in chat: `client.chat.create({ session_id, model: "iris-genesis", message: "A lighthouse at dawn" })` — images come back in `reply.payload.images`.

## Knowledge: answers from your own documents

```ts
const item = await client.knowledge.upload({ file: "handbook.pdf", title: "Team Handbook", tags: ["hr", "policy"] });
await client.knowledge.waitUntilProcessed(item.id);

const answer = await client.knowledge.ask({ question: "What is our remote-work policy?", tags: ["hr"] });
console.log(answer.answer);
for (const c of answer.citations) console.log("-", c.title, c.score.toFixed(2));
```

PDF, DOCX, TXT and Markdown, up to 20 MB. Plain text works too: `client.knowledge.create({ title, content })`.

## Error handling

```ts
import OpenQCore, { APIStatusError, APIConnectionError, InsufficientBalanceError, RateLimitError } from "openqcore";

try {
  await client.chat.create({ session_id: session.id, message: "Hi" });
} catch (err) {
  if (err instanceof InsufficientBalanceError) console.log("Top up your wallet");
  else if (err instanceof RateLimitError) console.log("Retry in", err.retryAfter, "s");
  else if (err instanceof APIStatusError) console.log(err.status, err.code, err.message, err.traceId);
  else if (err instanceof APIConnectionError) console.log("Network problem");
  else throw err;
}
```

| Status | Error class |
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
| 422 | `UnprocessableEntityError` (`details` has the field errors) |
| 429 | `RateLimitError` (`retryAfter`) |
| 503 | `ServiceUnavailableError` |
| 504 | `GatewayTimeoutError` |
| other 5xx | `InternalServerError` |

All extend `APIStatusError` → `APIError` → `OpenQCoreError`. Include `err.traceId` when you contact support.

## Retries, timeouts and cancellation

Requests are retried twice by default, with exponential backoff and the server's `Retry-After`: `429` and `503` for every request, network errors before the request reached the server, and `5xx` for reads. Each chat call carries a generated `request_id`, so a retried turn is never answered twice.

```ts
const client = new OpenQCore({ maxRetries: 5, timeout: 60_000 });

const controller = new AbortController();
await client.knowledge.ask({ question: "..." }, { timeout: 300_000, signal: controller.signal });
```

## Authentication

| You have | Use |
| --- | --- |
| An API key (servers, scripts) | `new OpenQCore({ apiKey })` or `OPENQCORE_API_KEY` |
| Email and password | `await OpenQCore.fromCredentials({ email, password })` |
| An access token | `new OpenQCore({ accessToken })` or `OPENQCORE_ACCESS_TOKEN` |

Managing API keys (`client.apiKeys`, `client.workspaceApiKeys`) needs a signed-in user, not an API key. The client refuses to use an API key in a browser unless you pass `dangerouslyAllowBrowser: true`; call OpenQCore from your server instead.

Run requests in a workspace with `new OpenQCore({ workspaceId })` (sent as `X-Workspace-ID`), or per chat call with `workspace_id`, `scope` and `agent_id`.

## Everything else

| Resource | Methods |
| --- | --- |
| `client.sessions` | `create`, `list`, `update`, `delete`, `messages` |
| `client.messages` | `retrieve`, `update`, `history`, `undo`, `delete` |
| `client.archive` | `create`, `list`, `retrieve`, `update`, `delete` |
| `client.apiKeys` | `create`, `list`, `revoke`, `disable` |
| `client.workspaceApiKeys` | `create`, `list`, `delete` |
| `client.search` / `client.rag` | `query` / `ask` |
| `client.ingest` / `client.embeddings` | `create` |
| `client.usage` | `me` |
| `client.auth` | `login`, `refresh` |

Request fields use the API's own names (`session_id`, `top_k`, …), so the [API reference](https://www.openqcore.com/docs/api) maps one to one.

## Links

- API documentation: https://www.openqcore.com/docs
- SDK overview: https://www.openqcore.com/developers/sdks
- Support: developers@openqcore.com

MIT licensed.
