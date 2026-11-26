import {
  APIConnectionError,
  APITimeoutError,
  APIUserAbortError,
  OpenQCoreError,
  errorFromResponse,
} from "./errors.js";
import { Stream } from "./streaming.js";
import type {
  ApiKey,
  ArchiveList,
  ArchiveUnit,
  ArchiveUnitInput,
  ChatChunk,
  ChatCompletion,
  ChatCreateParams,
  Job,
  JSONObject,
  KnowledgeAnswer,
  KnowledgeItem,
  Message,
  ModelInfo,
  OCRResult,
  Page,
  Session,
  Token,
  VoiceEvent,
} from "./types.js";
import { type FileLike, toUpload } from "./uploads.js";
import { VERSION } from "./version.js";

export const DEFAULT_BASE_URL = "https://api.openqcore.com/api/v1";

export interface ClientOptions {
  /** API key (X-API-Key). Defaults to process.env.OPENQCORE_API_KEY. */
  apiKey?: string | null;
  /** JWT from auth.login (Authorization: Bearer). Defaults to OPENQCORE_ACCESS_TOKEN. Needed to manage API keys. */
  accessToken?: string | null;
  /** Defaults to OPENQCORE_BASE_URL or https://api.openqcore.com/api/v1. */
  baseURL?: string;
  /** Sent as X-Workspace-ID on every request. Defaults to OPENQCORE_WORKSPACE_ID. */
  workspaceId?: string | null;
  /** Request timeout in ms. Default 120000. */
  timeout?: number;
  /** Retries for 429/503 and network failures. Default 2. */
  maxRetries?: number;
  defaultHeaders?: Record<string, string>;
  /** Custom fetch (proxies, tests, older runtimes). */
  fetch?: typeof fetch;
  /**
   * Using an API key in a browser exposes it to every visitor. Set this only
   * for internal tools where that is acceptable.
   */
  dangerouslyAllowBrowser?: boolean;
}

export interface RequestOptions {
  /** Override the timeout (ms) for this call. */
  timeout?: number;
  maxRetries?: number;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

interface InternalRequest {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  query?: Record<string, unknown>;
  json?: unknown;
  form?: Record<string, unknown>;
  files?: Record<string, { blob: Blob; filename: string }>;
  auth?: boolean;
  stream?: boolean;
  headers?: Record<string, string | undefined>;
  options?: RequestOptions;
}

const RETRY_ANY = new Set([429, 503]);
const RETRY_IDEMPOTENT = new Set([429, 500, 502, 503, 504]);
const IDEMPOTENT = new Set(["GET", "DELETE"]);

const env = (name: string): string | undefined => {
  try {
    return typeof process !== "undefined" ? process.env?.[name] || undefined : undefined;
  } catch {
    return undefined;
  }
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function uuid(): string {
  const c: any = (globalThis as any).crypto;
  if (c?.randomUUID) return c.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    return (ch === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function compact<T extends Record<string, unknown>>(obj: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) if (v !== undefined && v !== null) out[k] = v;
  return out as Partial<T>;
}

function liftChunk(obj: any): ChatChunk {
  const delta = obj?.choices?.[0]?.delta ?? {};
  const chunk: ChatChunk = { ...obj };
  if (typeof delta.content === "string" && delta.content) chunk.content = delta.content;
  if (delta.status && typeof delta.status === "object") chunk.status = delta.status;
  if (delta.payload && typeof delta.payload === "object" && Object.keys(delta.payload).length) chunk.payload = delta.payload;
  return chunk;
}

export class OpenQCore {
  apiKey: string | null;
  accessToken: string | null;
  baseURL: string;
  workspaceId: string | null;
  timeout: number;
  maxRetries: number;
  private readonly defaultHeaders: Record<string, string>;
  private readonly fetchImpl: typeof fetch;

  readonly auth = new Auth(this);
  readonly chat = new Chat(this);
  readonly sessions = new Sessions(this);
  readonly messages = new Messages(this);
  readonly voice = new Voice(this);
  readonly images = new Images(this);
  readonly videos = new Videos(this);
  readonly ocr = new OCR(this);
  readonly knowledge = new Knowledge(this);
  readonly archive = new Archive(this);
  readonly apiKeys = new ApiKeys(this);
  readonly workspaceApiKeys = new WorkspaceApiKeys(this);
  readonly models = new Models(this);
  readonly usage = new Usage(this);
  readonly search = new Search(this);
  readonly rag = new Rag(this);
  readonly embeddings = new Embeddings(this);
  readonly ingest = new Ingest(this);

  constructor(options: ClientOptions = {}) {
    this.apiKey = options.apiKey !== undefined ? options.apiKey : env("OPENQCORE_API_KEY") ?? null;
    this.accessToken = options.accessToken !== undefined ? options.accessToken : env("OPENQCORE_ACCESS_TOKEN") ?? null;
    this.baseURL = (options.baseURL ?? env("OPENQCORE_BASE_URL") ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.workspaceId = options.workspaceId !== undefined ? options.workspaceId : env("OPENQCORE_WORKSPACE_ID") ?? null;
    this.timeout = options.timeout ?? 120_000;
    this.maxRetries = options.maxRetries ?? 2;
    this.defaultHeaders = { ...(options.defaultHeaders ?? {}) };
    const f = options.fetch ?? (globalThis as any).fetch;
    if (!f) throw new OpenQCoreError("No fetch implementation found. Use Node.js 18+ or pass options.fetch.");
    this.fetchImpl = f.bind(globalThis);

    const isBrowser = typeof window !== "undefined" && typeof (window as any).document !== "undefined";
    if (isBrowser && this.apiKey && !options.dangerouslyAllowBrowser) {
      throw new OpenQCoreError(
        "Refusing to use an API key in the browser: it would be visible to every visitor. " +
          "Call OpenQCore from your server, or pass dangerouslyAllowBrowser: true for internal tools.",
      );
    }
  }

  /** Sign in with email and password and get a client that uses the access token. */
  static async fromCredentials(
    credentials: { email: string; password: string },
    options: Omit<ClientOptions, "apiKey" | "accessToken"> = {},
  ): Promise<OpenQCore> {
    const bootstrap = new OpenQCore({ ...options, apiKey: null, accessToken: null });
    const token = await bootstrap.auth.login(credentials);
    return new OpenQCore({ ...options, apiKey: null, accessToken: token.access_token });
  }

  /** A copy of this client with some options changed. */
  withOptions(options: ClientOptions): OpenQCore {
    return new OpenQCore({
      apiKey: this.apiKey,
      accessToken: this.accessToken,
      baseURL: this.baseURL,
      workspaceId: this.workspaceId,
      timeout: this.timeout,
      maxRetries: this.maxRetries,
      defaultHeaders: this.defaultHeaders,
      fetch: this.fetchImpl,
      dangerouslyAllowBrowser: true,
      ...options,
    });
  }

  private authHeaders(): Record<string, string> {
    if (this.apiKey) return { "X-API-Key": this.apiKey };
    if (this.accessToken) return { Authorization: `Bearer ${this.accessToken}` };
    throw new OpenQCoreError(
      "No credentials. Pass { apiKey } (or { accessToken }) to new OpenQCore(), or set OPENQCORE_API_KEY.",
    );
  }

  private buildURL(path: string, query?: Record<string, unknown>): string {
    const url = new URL(this.baseURL + path);
    if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    return url.toString();
  }

  /** @internal */
  async request(req: InternalRequest): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: req.stream ? "text/event-stream" : "application/json",
      "X-OpenQCore-SDK": `typescript/${VERSION}`,
    };
    if (typeof window === "undefined") headers["User-Agent"] = `openqcore-typescript/${VERSION}`;
    if (req.auth !== false) Object.assign(headers, this.authHeaders());
    if (this.workspaceId) headers["X-Workspace-ID"] = this.workspaceId;
    Object.assign(headers, this.defaultHeaders);
    for (const [k, v] of Object.entries(req.headers ?? {})) if (v !== undefined) headers[k] = v;
    Object.assign(headers, req.options?.headers ?? {});

    const url = this.buildURL(req.path, req.query);
    const maxRetries = req.options?.maxRetries ?? this.maxRetries;
    const timeout = req.options?.timeout ?? this.timeout;

    for (let attempt = 0; ; attempt++) {
      let body: BodyInit | undefined;
      const h = { ...headers };
      if (req.files || req.form) {
        const fd = new FormData();
        for (const [k, v] of Object.entries(req.form ?? {})) if (v !== undefined && v !== null) fd.append(k, String(v));
        for (const [k, f] of Object.entries(req.files ?? {})) fd.append(k, f.blob, f.filename);
        body = fd; // fetch sets the multipart boundary
      } else if (req.json !== undefined) {
        body = JSON.stringify(req.json);
        h["Content-Type"] = "application/json";
      }

      const controller = new AbortController();
      const userSignal = req.options?.signal;
      if (userSignal?.aborted) throw new APIUserAbortError();
      const onAbort = () => controller.abort();
      userSignal?.addEventListener("abort", onAbort, { once: true });
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeout);

      let response: Response;
      try {
        response = await this.fetchImpl(url, { method: req.method, headers: h, body, signal: controller.signal });
      } catch (err) {
        clearTimeout(timer);
        userSignal?.removeEventListener("abort", onAbort);
        if (userSignal?.aborted) throw new APIUserAbortError();
        const canRetry = attempt < maxRetries && (IDEMPOTENT.has(req.method) || !timedOut);
        if (canRetry) {
          await sleep(this.backoff(attempt, null));
          continue;
        }
        if (timedOut) throw new APITimeoutError();
        throw new APIConnectionError(`Connection error: ${(err as Error)?.message ?? err}`, err);
      }

      // For streams the timeout covers the connection, not the whole stream.
      clearTimeout(timer);

      if (response.ok) {
        if (req.stream) (response as any)._oqcController = controller;
        else userSignal?.removeEventListener("abort", onAbort);
        return response;
      }

      const retryable = RETRY_ANY.has(response.status) || (IDEMPOTENT.has(req.method) && RETRY_IDEMPOTENT.has(response.status));
      if (attempt < maxRetries && retryable) {
        const delay = this.backoff(attempt, response);
        await response.body?.cancel().catch(() => undefined);
        await sleep(delay);
        continue;
      }
      const text = await response.text().catch(() => "");
      userSignal?.removeEventListener("abort", onAbort);
      throw errorFromResponse(response.status, response.headers, text);
    }
  }

  private backoff(attempt: number, response: Response | null): number {
    const header = response?.headers.get("retry-after");
    if (header) {
      const s = Number(header);
      if (Number.isFinite(s)) return Math.min(Math.max(s, 0), 60) * 1000;
    }
    const base = Math.min(500 * 2 ** attempt, 8000);
    return base * (0.75 + Math.random() * 0.5);
  }

  /** @internal */
  async json<T>(req: InternalRequest): Promise<T> {
    const res = await this.request(req);
    const text = await res.text();
    return (text ? JSON.parse(text) : {}) as T;
  }

  /** @internal */
  async bytes(req: InternalRequest): Promise<Uint8Array> {
    const res = await this.request(req);
    return new Uint8Array(await res.arrayBuffer());
  }

  /** @internal */
  async stream<T>(req: InternalRequest, cast: (o: any) => T, opts?: { doneMarker: boolean; isFinal: (o: any) => boolean }): Promise<Stream<T>> {
    const res = await this.request({ ...req, stream: true });
    return new Stream<T>(res, (res as any)._oqcController, cast, opts);
  }
}

abstract class Resource {
  constructor(protected readonly client: OpenQCore) {}
}

// ======================================================================= auth

export class Auth extends Resource {
  /** Exchange email and password for an access token (JWT). */
  login(body: { email: string; password: string }, options?: RequestOptions): Promise<Token> {
    return this.client.json({ method: "POST", path: "/auth/login", json: body, auth: false, options });
  }

  /** Get a fresh access token for the current one (must not be expired). */
  refresh(options?: RequestOptions): Promise<Token> {
    return this.client.json({ method: "POST", path: "/auth/refresh", options });
  }
}

// ======================================================================= chat

function chatRequest(params: ChatCreateParams, stream: boolean, options?: RequestOptions): InternalRequest {
  const { workspace_id, scope, agent_id, ...rest } = params;
  if (rest.message === undefined && !rest.messages?.length) throw new OpenQCoreError("Pass message or messages.");
  return {
    method: "POST",
    path: "/chat/completions",
    json: compact({ ...rest, stream, request_id: rest.request_id ?? uuid() }),
    headers: { "X-Workspace-ID": workspace_id, "X-Scope-Type": scope, "X-Agent-ID": agent_id },
    options,
  };
}

export class Chat extends Resource {
  /** Send one turn and wait for the full reply. The session must exist (`sessions.create`). */
  create(params: ChatCreateParams, options?: RequestOptions): Promise<ChatCompletion> {
    return this.client.json(chatRequest(params, false, options));
  }

  /** Send one turn and stream the reply. */
  stream(params: ChatCreateParams, options?: RequestOptions): Promise<Stream<ChatChunk>> {
    return this.client.stream(chatRequest(params, true, options), liftChunk);
  }

  health(options?: RequestOptions): Promise<{ status: string; service: string }> {
    return this.client.json({ method: "GET", path: "/chat/health", auth: false, options });
  }
}

// ======================================================================= sessions

export class Sessions extends Resource {
  create(
    body: { title?: string; folder_id?: string; workspace_id?: string; agent_id?: string } = {},
    options?: RequestOptions,
  ): Promise<Session> {
    return this.client.json({ method: "POST", path: "/sessions", json: compact(body), options });
  }

  list(
    query: { kind?: string; agent_id?: string; pinned?: boolean; limit?: number; offset?: number } = {},
    options?: RequestOptions,
  ): Promise<Page<Session>> {
    return this.client.json({ method: "GET", path: "/sessions", query, options });
  }

  update(
    sessionId: string,
    body: { title?: string; pinned?: boolean; starred?: boolean; marked_unread?: boolean; folder_id?: string },
    options?: RequestOptions,
  ): Promise<JSONObject> {
    const json = compact(body);
    if (!Object.keys(json).length) throw new OpenQCoreError("Nothing to update.");
    return this.client.json({ method: "PATCH", path: `/sessions/${sessionId}`, json, options });
  }

  delete(sessionId: string, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "DELETE", path: `/sessions/${sessionId}`, options });
  }

  /** All messages of a session, oldest first. */
  messages(sessionId: string, options?: RequestOptions): Promise<Page<Message>> {
    return this.client.json({ method: "GET", path: `/sessions/${sessionId}/messages`, options });
  }
}

export class Messages extends Resource {
  retrieve(messageId: string, options?: RequestOptions): Promise<Message> {
    return this.client.json({ method: "GET", path: `/messages/${messageId}`, options });
  }
  update(messageId: string, body: { content: string; payload?: JSONObject }, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "PATCH", path: `/messages/${messageId}`, json: compact(body), options });
  }
  history(messageId: string, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "GET", path: `/messages/${messageId}/history`, options });
  }
  undo(messageId: string, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: `/messages/${messageId}/undo`, options });
  }
  delete(messageId: string, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "DELETE", path: `/messages/${messageId}`, options });
  }
}

// ======================================================================= voice

const audio = (file: FileLike) => toUpload(file, { defaultName: "audio.wav", forceTypePrefix: "audio/" });

export class Voice extends Resource {
  /**
   * Upload a recording; stream the transcript, reply text and spoken audio chunks.
   * Events: user_text, status, text_delta, audio_chunk_ready, then done (or error).
   */
  async stream(params: { file: FileLike; session_id: string; model?: string }, options?: RequestOptions): Promise<Stream<VoiceEvent>> {
    return this.client.stream(
      {
        method: "POST",
        path: "/voice/chat/meta",
        form: { model: params.model ?? "pulse", session_id: params.session_id },
        files: { file: await audio(params.file) },
        options,
      },
      (o) => o as VoiceEvent,
      { doneMarker: false, isFinal: (o) => o?.type === "done" || o?.type === "error" },
    );
  }

  /** The whole reply of a finished voice turn as one MP3 (values come from the `done` event). */
  async replyAudio(
    params: {
      file: FileLike;
      session_id: string;
      user_text: string;
      response_text: string;
      user_request_id: string;
      assistant_request_id: string;
      model?: string;
    },
    options?: RequestOptions,
  ): Promise<Uint8Array> {
    const { file, model, ...rest } = params;
    return this.client.bytes({
      method: "POST",
      path: "/voice/chat",
      form: { ...rest, model: model ?? "pulse" },
      files: { file: await audio(file) },
      options,
    });
  }

  /** Text to speech (up to 5,000 characters). Returns MP3 bytes. */
  speech(params: { text: string; language?: string }, options?: RequestOptions): Promise<Uint8Array> {
    return this.client.bytes({ method: "POST", path: "/voice/tts", form: params, options });
  }

  /** Stop the reply currently being generated for the session. */
  interrupt(sessionId: string, options?: RequestOptions): Promise<{ status: string; session_id: string }> {
    return this.client.json({ method: "POST", path: `/voice/interrupt/${sessionId}`, options });
  }
}

// ======================================================================= iris

const FINISHED = new Set(["done", "failed", "blocked"]);

async function waitForJob(get: () => Promise<Job>, id: string, timeoutMs: number, pollMs: number): Promise<Job> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = await get();
    if (FINISHED.has(job.status)) return job;
    if (Date.now() >= deadline) throw new OpenQCoreError(`Job ${id} did not finish in time (last status: ${job.status}).`);
    await sleep(pollMs);
  }
}

export interface ImageGenerateParams {
  prompt: string;
  size?: "512x512" | "768x768" | "1024x1024" | "1024x1536" | "1536x1024";
  steps?: number;
  guidance?: number;
  seed?: number;
  num_outputs?: number;
  policy_mode?: "off" | "soft" | "strict";
  provider?: "stability" | "fal" | "replicate" | "runpod";
}

export class Images extends Resource {
  /** Generate images. Needs a workspace API key. */
  generate(params: ImageGenerateParams, options?: RequestOptions): Promise<Job> {
    return this.client.json({ method: "POST", path: "/images/generate", json: compact({ ...params }), options });
  }
  retrieve(jobId: string, options?: RequestOptions): Promise<Job> {
    return this.client.json({ method: "GET", path: `/images/jobs/${jobId}`, options });
  }
  download(jobId: string, params: { index?: number } = {}, options?: RequestOptions): Promise<Uint8Array> {
    return this.client.bytes({ method: "GET", path: `/images/jobs/${jobId}/download`, query: { index: params.index ?? 0 }, options });
  }
  /** Poll until the job is done, failed or blocked. */
  wait(jobId: string, opts: { timeoutMs?: number; pollIntervalMs?: number } = {}): Promise<Job> {
    return waitForJob(() => this.retrieve(jobId), jobId, opts.timeoutMs ?? 300_000, opts.pollIntervalMs ?? 2000);
  }
}

export class Videos extends Resource {
  generate(
    params: { prompt: string; length?: number; steps?: number; target_size?: number; cfg?: number; image?: string },
    options?: RequestOptions,
  ): Promise<Job> {
    return this.client.json({ method: "POST", path: "/videos/generate", json: compact({ ...params }), options });
  }
  retrieve(jobId: string, options?: RequestOptions): Promise<Job> {
    return this.client.json({ method: "GET", path: `/videos/jobs/${jobId}`, options });
  }
  wait(jobId: string, opts: { timeoutMs?: number; pollIntervalMs?: number } = {}): Promise<Job> {
    return waitForJob(() => this.retrieve(jobId), jobId, opts.timeoutMs ?? 900_000, opts.pollIntervalMs ?? 5000);
  }
}

export class OCR extends Resource {
  /** Read a document or ID image: text, document type, structured fields and risk checks. */
  async extract(params: { file: FileLike }, options?: RequestOptions): Promise<OCRResult> {
    return this.client.json({
      method: "POST",
      path: "/ocr/generate",
      files: { file: await toUpload(params.file, { defaultName: "document" }) },
      options,
    });
  }
}

// ======================================================================= knowledge

const K = "/console/knowledge";

export class Knowledge extends Resource {
  list(query: { limit?: number; offset?: number; status?: string } = {}, options?: RequestOptions): Promise<Page<KnowledgeItem>> {
    return this.client.json({ method: "GET", path: K, query, options });
  }

  /** Add plain text. Indexed in the background (status starts as "processing"). */
  create(body: { title: string; content: string; description?: string; tags?: string[] }, options?: RequestOptions): Promise<KnowledgeItem> {
    return this.client.json({ method: "POST", path: K, json: compact(body), options });
  }

  /** Upload a PDF, DOCX, TXT or Markdown file (max 20 MB). */
  async upload(
    params: { file: FileLike; title?: string; description?: string; tags?: string[] | string },
    options?: RequestOptions,
  ): Promise<KnowledgeItem> {
    const tags = Array.isArray(params.tags) ? params.tags.join(",") : params.tags;
    return this.client.json({
      method: "POST",
      path: `${K}/upload`,
      form: { title: params.title, description: params.description, tags },
      files: { file: await toUpload(params.file, { defaultName: "document" }) },
      options,
    });
  }

  retrieve(knowledgeId: string, options?: RequestOptions): Promise<KnowledgeItem> {
    return this.client.json({ method: "GET", path: `${K}/${knowledgeId}`, options });
  }

  update(knowledgeId: string, body: { title?: string; description?: string; tags?: string[] }, options?: RequestOptions): Promise<KnowledgeItem> {
    const json = compact(body);
    if (!Object.keys(json).length) throw new OpenQCoreError("Nothing to update.");
    return this.client.json({ method: "PATCH", path: `${K}/${knowledgeId}`, json, options });
  }

  delete(knowledgeId: string, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "DELETE", path: `${K}/${knowledgeId}`, options });
  }

  /** Answer a question from your processed items, with citations. */
  ask(
    body: { question: string; top_k?: number; min_score?: number; item_ids?: string[]; tags?: string[]; model?: string },
    options?: RequestOptions,
  ): Promise<KnowledgeAnswer> {
    return this.client.json({ method: "POST", path: `${K}/ask`, json: compact(body), options });
  }

  /** Poll until indexing finishes. Rejects if it failed. */
  async waitUntilProcessed(knowledgeId: string, opts: { timeoutMs?: number; pollIntervalMs?: number } = {}): Promise<KnowledgeItem> {
    const deadline = Date.now() + (opts.timeoutMs ?? 300_000);
    for (;;) {
      const item = await this.retrieve(knowledgeId);
      if (item.status === "processed") return item;
      if (item.status === "failed") throw new OpenQCoreError(`Indexing failed for ${knowledgeId}: ${item.error_msg ?? "unknown error"}`);
      if (Date.now() >= deadline) throw new OpenQCoreError(`${knowledgeId} was not processed in time (status: ${item.status}).`);
      await sleep(opts.pollIntervalMs ?? 2000);
    }
  }
}

// ======================================================================= archive

export class Archive extends Resource {
  create(body: ArchiveUnitInput, options?: RequestOptions): Promise<ArchiveUnit> {
    return this.client.json({ method: "POST", path: "/archive/units", json: compact({ ...body }), options });
  }
  list(query: { category?: string; engine_scope?: string; limit?: number; offset?: number } = {}, options?: RequestOptions): Promise<ArchiveList> {
    return this.client.json({ method: "GET", path: "/archive/units", query, options });
  }
  retrieve(unitId: string, options?: RequestOptions): Promise<ArchiveUnit> {
    return this.client.json({ method: "GET", path: `/archive/units/${unitId}`, options });
  }
  update(unitId: string, body: ArchiveUnitInput, options?: RequestOptions): Promise<ArchiveUnit> {
    const json = compact({ ...body });
    if (!Object.keys(json).length) throw new OpenQCoreError("Nothing to update.");
    return this.client.json({ method: "PATCH", path: `/archive/units/${unitId}`, json, options });
  }
  delete(unitId: string, options?: RequestOptions): Promise<{ ok: boolean }> {
    return this.client.json({ method: "DELETE", path: `/archive/units/${unitId}`, options });
  }
}

// ======================================================================= api keys

/** Personal API keys. Needs a signed-in user (accessToken), not an API key. */
export class ApiKeys extends Resource {
  /** The full key is only returned here: store it right away. */
  create(body: { name?: string } = {}, options?: RequestOptions): Promise<ApiKey> {
    return this.client.json({ method: "POST", path: "/api-keys", json: compact(body), options });
  }
  list(options?: RequestOptions): Promise<ApiKey[]> {
    return this.client.json({ method: "GET", path: "/api-keys", options });
  }
  revoke(keyId: number, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: `/api-keys/${keyId}/revoke`, options });
  }
  disable(keyId: number, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: `/api-keys/${keyId}/disable`, options });
  }
}

/** Workspace API keys. Needs a signed-in workspace admin. */
export class WorkspaceApiKeys extends Resource {
  create(
    workspaceId: string,
    body: { name: string; scopes?: string; daily_limit?: number; monthly_token_limit?: number; is_unlimited?: boolean },
    options?: RequestOptions,
  ): Promise<ApiKey> {
    return this.client.json({ method: "POST", path: `/workspaces/${workspaceId}/api-keys`, json: compact(body), options });
  }
  async list(workspaceId: string, options?: RequestOptions): Promise<ApiKey[]> {
    const res = await this.client.json<{ items?: ApiKey[] }>({ method: "GET", path: `/workspaces/${workspaceId}/api-keys`, options });
    return res.items ?? [];
  }
  delete(workspaceId: string, keyId: number, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "DELETE", path: `/workspaces/${workspaceId}/api-keys/${keyId}`, options });
  }
}

// ======================================================================= models / usage / retrieval

export class Models extends Resource {
  /** Models you can pass as `model` (`product_key: "chat"` for chat models only). */
  list(query: { product_key?: string } = {}, options?: RequestOptions): Promise<{ object: "list"; data: ModelInfo[] }> {
    return this.client.json({ method: "GET", path: "/models/", query, auth: false, options });
  }
}

export class Usage extends Resource {
  /** Usage of the API key making the call. */
  me(options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "GET", path: "/usage/me", options });
  }
}

export class Search extends Resource {
  query(body: { query: string; top_k?: number; source?: string; country?: string }, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: "/search", json: compact(body), options });
  }
}

export class Rag extends Resource {
  ask(
    body: {
      question: string;
      top_k?: number;
      min_score?: number;
      min_hits?: number;
      country?: string;
      source?: string;
      lang?: string;
      model?: string;
      temperature?: number;
    },
    options?: RequestOptions,
  ): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: "/rag/ask", json: compact(body), options });
  }
}

export class Embeddings extends Resource {
  create(body: { input: string | string[]; model?: string }, options?: RequestOptions): Promise<JSONObject> {
    return this.client.json({ method: "POST", path: "/embeddings", json: compact(body), options });
  }
}

export class Ingest extends Resource {
  /** Add text to your private retrieval corpus (used by search and rag). */
  create(body: { items: Array<string | { content: string; metadata?: JSONObject }> }, options?: RequestOptions): Promise<JSONObject> {
    const items = body.items.map((i) => (typeof i === "string" ? { content: i } : i));
    if (!items.length) throw new OpenQCoreError("items must not be empty.");
    return this.client.json({ method: "POST", path: "/ingest", json: { items }, options });
  }
}
