import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

import OpenQCore, {
  APIConnectionError,
  AuthenticationError,
  InsufficientBalanceError,
  InternalServerError,
  NotFoundError,
  OpenQCoreError,
  RateLimitError,
  StreamError,
  UnprocessableEntityError,
  VERSION,
} from "../dist/esm/index.js";

const BASE = "https://api.test/api/v1";
const SESSION = "2d6c9a51-6f4c-4c43-9c2d-7a3f1c1a9e10";

for (const v of ["OPENQCORE_API_KEY", "OPENQCORE_ACCESS_TOKEN", "OPENQCORE_BASE_URL", "OPENQCORE_WORKSPACE_ID"]) delete process.env[v];

/** A fetch mock that records requests and answers from a handler. */
function mockFetch(handler) {
  const calls = [];
  const fn = async (url, init) => {
    const req = { url: new URL(url), method: init.method, headers: new Headers(init.headers), body: init.body };
    if (typeof init.body === "string") req.json = JSON.parse(init.body);
    if (init.body instanceof FormData) req.form = init.body;
    calls.push(req);
    return handler(req, calls.length);
  };
  fn.calls = calls;
  fn.last = () => calls[calls.length - 1];
  return fn;
}

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

const envelope = (status, code, message, extra = {}) =>
  json(status, { success: false, error: { code, message, trace_id: "tr-1", extra } });

const sse = (...events) =>
  new Response(events.map((e) => `data: ${typeof e === "string" ? e : JSON.stringify(e)}\n\n`).join(""), {
    headers: { "content-type": "text/event-stream" },
  });

const chunk = (delta) => ({ id: "r1", choices: [{ delta }] });

const make = (handler, opts = {}) => {
  const fetch = mockFetch(handler);
  const client = new OpenQCore({ apiKey: "oqc_live_test", baseURL: BASE, fetch, ...opts });
  // no real waiting in tests
  client.backoff = () => 0;
  return { client, fetch };
};

// ------------------------------------------------------------------ auth & headers

test("api key, sdk header and workspace header", async () => {
  const { client, fetch } = make(() => json(200, { ok: true }), { workspaceId: "ws-1" });
  await client.usage.me();
  const h = fetch.last().headers;
  assert.equal(h.get("x-api-key"), "oqc_live_test");
  assert.equal(h.get("authorization"), null);
  assert.equal(h.get("x-workspace-id"), "ws-1");
  assert.equal(h.get("x-openqcore-sdk"), `typescript/${VERSION}`);
  assert.equal(fetch.last().url.toString(), `${BASE}/usage/me`);
});

test("access token from env", async () => {
  process.env.OPENQCORE_ACCESS_TOKEN = "jwt-1";
  try {
    const { client, fetch } = make(() => json(200, []), { apiKey: undefined });
    await client.apiKeys.list();
    assert.equal(fetch.last().headers.get("authorization"), "Bearer jwt-1");
  } finally {
    delete process.env.OPENQCORE_ACCESS_TOKEN;
  }
});

test("missing credentials give a clear error", async () => {
  const { client } = make(() => json(200, {}), { apiKey: null });
  await assert.rejects(client.sessions.list(), (e) => e instanceof OpenQCoreError && /OPENQCORE_API_KEY/.test(e.message));
});

test("models.list is public", async () => {
  const { client, fetch } = make(() => json(200, { object: "list", data: [{ id: "pulse" }] }), { apiKey: null });
  const res = await client.models.list({ product_key: "chat" });
  assert.equal(res.data[0].id, "pulse");
  assert.equal(fetch.last().url.searchParams.get("product_key"), "chat");
  assert.equal(fetch.last().headers.get("x-api-key"), null);
});

test("fromCredentials signs in and uses the token", async () => {
  process.env.OPENQCORE_API_KEY = "must-not-be-used";
  try {
    const fetch = mockFetch((req) =>
      req.url.pathname.endsWith("/auth/login") ? json(200, { access_token: "jwt-9", token_type: "bearer" }) : json(200, []),
    );
    const client = await OpenQCore.fromCredentials({ email: "a@b.co", password: "pw" }, { baseURL: BASE, fetch });
    await client.apiKeys.list();
    assert.deepEqual(fetch.calls[0].json, { email: "a@b.co", password: "pw" });
    assert.equal(fetch.calls[0].headers.get("x-api-key"), null);
    assert.equal(fetch.calls[1].headers.get("authorization"), "Bearer jwt-9");
  } finally {
    delete process.env.OPENQCORE_API_KEY;
  }
});

// ------------------------------------------------------------------ chat

test("chat.create body, headers and response", async () => {
  const reply = { id: "m1", content: "Hi!", usage: { total_tokens: 5 }, payload: { images: [] } };
  const { client, fetch } = make(() => json(200, reply));
  const out = await client.chat.create({ session_id: SESSION, message: "Hello", model: "pulse", scope: "workspace", workspace_id: "ws-2" });
  const req = fetch.last();
  assert.equal(req.json.session_id, SESSION);
  assert.equal(req.json.stream, false);
  assert.match(req.json.request_id, /^[0-9a-f-]{36}$/);
  assert.equal(req.json.scope, undefined);
  assert.equal(req.headers.get("x-scope-type"), "workspace");
  assert.equal(req.headers.get("x-workspace-id"), "ws-2");
  assert.equal(req.headers.get("content-type"), "application/json");
  assert.equal(out.content, "Hi!");
});

test("chat needs a message", () => {
  const { client } = make(() => json(200, {}));
  assert.throws(() => client.chat.create({ session_id: SESSION }), OpenQCoreError);
});

test("chat.stream lifts content, status and payload", async () => {
  const { client, fetch } = make(() =>
    sse(chunk({ status: { stage: "thinking" } }), chunk({ content: "Hel" }), ": keep-alive", chunk({ content: "lo" }), chunk({ payload: { images: ["https://x/1.png"] } }), "[DONE]"),
  );
  const stream = await client.chat.stream({ session_id: SESSION, message: "hey" });
  const events = [];
  for await (const c of stream) events.push(c);
  assert.equal(fetch.last().headers.get("accept"), "text/event-stream");
  assert.equal(fetch.last().json.stream, true);
  assert.equal(events[0].status.stage, "thinking");
  assert.equal(events[0].content, undefined);
  assert.equal(events.map((e) => e.content ?? "").join(""), "Hello");
  assert.deepEqual(events.at(-1).payload.images, ["https://x/1.png"]);
});

test("stream.text() and lines split across network chunks", async () => {
  const body = new ReadableStream({
    start(c) {
      const enc = new TextEncoder();
      for (const part of ['data: {"choices":[{"delta":{"con', 'tent":"a"}}]}\r\n\r\nda', 'ta: {"choices":[{"delta":{"content":"b"}}]}\n\ndata: [DONE]\n\n']) c.enqueue(enc.encode(part));
      c.close();
    },
  });
  const { client } = make(() => new Response(body, { headers: { "content-type": "text/event-stream" } }));
  const stream = await client.chat.stream({ session_id: SESSION, message: "x" });
  assert.equal(await stream.text(), "ab");
});

test("a stream that is cut off raises StreamError", async () => {
  const { client } = make(() => sse(chunk({ content: "partial" })));
  const stream = await client.chat.stream({ session_id: SESSION, message: "x" });
  await assert.rejects(stream.text(), StreamError);
});

test("402 before the stream starts", async () => {
  const { client } = make(() => envelope(402, "WALLET_EXHAUSTED", "Balance used up"), { maxRetries: 0 });
  await assert.rejects(client.chat.stream({ session_id: SESSION, message: "x" }), (e) => e instanceof InsufficientBalanceError && e.code === "WALLET_EXHAUSTED");
});

// ------------------------------------------------------------------ errors & retries

test("error envelope -> typed error", async () => {
  const { client } = make(() => envelope(404, "SESSION_NOT_FOUND", "Session not found"));
  await assert.rejects(client.sessions.messages(SESSION), (e) => {
    assert.ok(e instanceof NotFoundError);
    assert.equal(e.status, 404);
    assert.equal(e.code, "SESSION_NOT_FOUND");
    assert.equal(e.traceId, "tr-1");
    assert.match(e.message, /SESSION_NOT_FOUND.*tr-1/);
    return true;
  });
});

test("422 details and plain detail bodies", async () => {
  const details = [{ loc: ["body", "session_id"], msg: "Input should be a valid UUID" }];
  const { client } = make(() => envelope(422, "VALIDATION_ERROR", "Invalid request payload.", { details }));
  await assert.rejects(client.chat.create({ session_id: "nope", message: "x" }), (e) => e instanceof UnprocessableEntityError && Array.isArray(e.details) && e.details[0].msg === details[0].msg);
  const { client: c2 } = make(() => json(401, { detail: "Not authenticated" }));
  await assert.rejects(c2.sessions.list(), (e) => e instanceof AuthenticationError && /Not authenticated/.test(e.message));
});

test("429 is retried, then succeeds", async () => {
  const { client, fetch } = make((_req, n) => (n === 1 ? json(429, { detail: "slow" }, { "retry-after": "1" }) : json(200, { id: SESSION })));
  const s = await client.sessions.create({ title: "t" });
  assert.equal(s.id, SESSION);
  assert.equal(fetch.calls.length, 2);
});

test("429 after retries exposes retryAfter", async () => {
  const { client, fetch } = make(() => json(429, { detail: "x" }, { "retry-after": "7" }), { maxRetries: 1 });
  await assert.rejects(client.sessions.create(), (e) => e instanceof RateLimitError && e.retryAfter === 7);
  assert.equal(fetch.calls.length, 2);
});

test("POST is not retried on 500, GET is retried on 502", async () => {
  const a = make(() => json(500, { detail: "boom" }));
  await assert.rejects(a.client.sessions.create(), InternalServerError);
  assert.equal(a.fetch.calls.length, 1);
  const b = make(() => json(502, { detail: "bad gateway" }));
  await assert.rejects(b.client.sessions.list(), InternalServerError);
  assert.equal(b.fetch.calls.length, 3);
});

test("network errors become APIConnectionError", async () => {
  const { client, fetch } = make(() => {
    throw new TypeError("fetch failed");
  }, { maxRetries: 1 });
  await assert.rejects(client.sessions.list(), APIConnectionError);
  assert.equal(fetch.calls.length, 2);
});

// ------------------------------------------------------------------ sessions, voice, iris, knowledge

test("sessions routes", async () => {
  const { client, fetch } = make(() => json(200, { items: [{ id: SESSION }], total: 1 }));
  const page = await client.sessions.list({ pinned: true, limit: 20 });
  assert.equal(fetch.last().url.searchParams.get("pinned"), "true");
  assert.equal(page.items[0].id, SESSION);
  await client.sessions.update(SESSION, { title: "Renamed" });
  assert.equal(fetch.last().method, "PATCH");
  assert.deepEqual(fetch.last().json, { title: "Renamed" });
  assert.throws(() => client.sessions.update(SESSION, {}), OpenQCoreError);
});

test("voice.stream sends multipart with an audio type and ends at done", async () => {
  const { client, fetch } = make(() =>
    sse(
      { type: "user_text", text: "Book a call" },
      { type: "text_delta", delta: "Sure" },
      { type: "audio_chunk_ready", audio_url: "https://x/1.mp3" },
      { type: "done", response_text: "Sure" },
    ),
  );
  const stream = await client.voice.stream({ file: { data: new Uint8Array([1, 2]), filename: "q.webm" }, session_id: SESSION });
  const types = [];
  for await (const e of stream) types.push(e.type);
  assert.deepEqual(types, ["user_text", "text_delta", "audio_chunk_ready", "done"]);
  const form = fetch.last().form;
  assert.equal(form.get("session_id"), SESSION);
  assert.equal(form.get("model"), "pulse");
  assert.equal(form.get("file").type, "audio/webm");
  assert.equal(form.get("file").name, "q.webm");
});

test("voice bytes without an audio type get one; tts returns bytes", async () => {
  const { client, fetch } = make(() => new Response(new Uint8Array([73, 68, 51])));
  const out = await client.voice.speech({ text: "Hi", language: "en" });
  assert.deepEqual([...out], [73, 68, 51]);
  assert.equal(fetch.last().form.get("text"), "Hi");
  await client.voice.replyAudio({
    file: new Uint8Array([1]),
    session_id: SESSION,
    user_text: "a",
    response_text: "b",
    user_request_id: "u",
    assistant_request_id: "a",
  });
  assert.match(fetch.last().form.get("file").type, /^audio\//);
});

test("image job: generate, wait, download", async () => {
  const states = ["queued", "running", "done"];
  const { client, fetch } = make((req) => {
    if (req.url.pathname.endsWith("/download")) return new Response(new Uint8Array([137, 80]));
    if (req.method === "POST") return json(200, { job_id: "j1", status: "queued" });
    return json(200, { job_id: "j1", status: states.shift(), output: ["https://x/1.png"] });
  });
  const job = await client.images.generate({ prompt: "mug", size: "1024x1024", num_outputs: 2 });
  assert.deepEqual(fetch.calls[0].json, { prompt: "mug", size: "1024x1024", num_outputs: 2 });
  const done = await client.images.wait(job.job_id, { pollIntervalMs: 0 });
  assert.equal(done.status, "done");
  const png = await client.images.download("j1", { index: 1 });
  assert.equal(png.length, 2);
  assert.equal(fetch.last().url.searchParams.get("index"), "1");
});

test("knowledge upload fields and failure while waiting", async () => {
  const { client, fetch } = make((req) =>
    req.method === "POST" ? json(202, { id: "k1", status: "processing" }) : json(200, { id: "k1", status: "failed", error_msg: "Unreadable PDF" }),
  );
  const blob = new Blob(["PK.."]);
  const item = await client.knowledge.upload({ file: { data: blob, filename: "handbook.docx" }, title: "Handbook", tags: ["hr", "policy"] });
  const form = fetch.last().form;
  assert.equal(item.status, "processing");
  assert.equal(form.get("tags"), "hr,policy");
  assert.equal(form.get("description"), null);
  assert.match(form.get("file").type, /wordprocessingml/);
  await assert.rejects(client.knowledge.waitUntilProcessed("k1", { pollIntervalMs: 0 }), /Unreadable PDF/);
});

test("knowledge.ask, archive, ingest and workspace keys", async () => {
  const { client, fetch } = make((req) => (req.url.pathname.includes("/workspaces/") ? json(200, { items: [{ id: 4 }], total: 1 }) : json(200, { ok: true })));
  await client.knowledge.ask({ question: "Remote policy?", top_k: 3, tags: ["hr"] });
  assert.deepEqual(fetch.last().json, { question: "Remote policy?", top_k: 3, tags: ["hr"] });
  await client.archive.create({ title: "Decision", confidence: 0.9 });
  assert.deepEqual(fetch.last().json, { title: "Decision", confidence: 0.9 });
  await client.ingest.create({ items: ["plain", { content: "meta", metadata: { a: 1 } }] });
  assert.deepEqual(fetch.last().json.items[0], { content: "plain" });
  const keys = await client.workspaceApiKeys.list("ws");
  assert.equal(keys[0].id, 4);
});

test("file paths work in Node", async () => {
  const { writeFile, mkdtemp } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const { tmpdir } = await import("node:os");
  const dir = await mkdtemp(join(tmpdir(), "oqc-"));
  const p = join(dir, "notes.md");
  await writeFile(p, "# Notes");
  const { client, fetch } = make(() => json(202, { id: "k2", status: "processing" }));
  await client.knowledge.upload({ file: p });
  const f = fetch.last().form.get("file");
  assert.equal(f.name, "notes.md");
  assert.equal(f.type, "text/markdown");
});

test("timeouts become APITimeoutError", async () => {
  const slowFetch = (_url, init) =>
    new Promise((_r, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
  const client = new OpenQCore({ apiKey: "k", baseURL: BASE, fetch: slowFetch, timeout: 20, maxRetries: 0 });
  await assert.rejects(client.sessions.list(), (e) => e.name === "APITimeoutError");
});

test("CommonJS build works", () => {
  const require = createRequire(import.meta.url);
  const cjs = require("../dist/cjs/index.js");
  assert.equal(typeof cjs.OpenQCore, "function");
  assert.equal(cjs.default, cjs.OpenQCore);
  assert.ok(new cjs.NotFoundError(404, "x", { headers: new Headers() }) instanceof cjs.APIStatusError);
});
