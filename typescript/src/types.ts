/**
 * Response and request types. Responses are plain JSON objects; fields the
 * API adds later appear at runtime even before these types list them.
 */

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface MediaPayload {
  images: string[];
  files: unknown[];
  videos: unknown[];
  documents: unknown[];
}

export interface ChatCompletion {
  id: string;
  message_id: string;
  content: string;
  session_id: string;
  model: string;
  payload: MediaPayload;
  usage: Usage;
  meta: { trace_id: string; request_id: string; execution_time_ms: number; cached: boolean; [k: string]: unknown };
  [k: string]: unknown;
}

export interface ChatStatus {
  stage: "thinking" | "searching" | "reviewing" | "writing" | "analyzing" | (string & {});
  detail?: string;
}

/** One streamed chat event. `content`, `status` and `payload` are lifted from `choices[0].delta`. */
export interface ChatChunk {
  id?: string;
  choices: Array<{ delta: { content?: string; status?: ChatStatus; payload?: Partial<MediaPayload> } }>;
  /** The next piece of text, if this chunk carries text. */
  content?: string;
  /** A progress update (thinking, searching…), if this chunk carries one. */
  status?: ChatStatus;
  /** Media produced during the turn, if this chunk carries any. */
  payload?: Partial<MediaPayload>;
  [k: string]: unknown;
}

export interface ChatMessageInput {
  role: "user" | "assistant" | "system" | (string & {});
  content: unknown;
  [k: string]: unknown;
}

export interface ChatCreateParams {
  /** Required. The id returned by `sessions.create`. */
  session_id: string;
  message?: string;
  messages?: ChatMessageInput[];
  /** Model slug; see `models.list()`. */
  model?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: unknown[];
  tool_choice?: unknown;
  metadata?: Record<string, unknown>;
  /** Idempotency key. Generated when omitted so retries never answer twice. */
  request_id?: string;
  /** Run this turn in a workspace (X-Workspace-ID). */
  workspace_id?: string;
  /** "personal" | "workspace" (X-Scope-Type). */
  scope?: "personal" | "workspace";
  /** Agent to run the turn with (X-Agent-ID). */
  agent_id?: string;
}

export interface Session {
  id: string;
  kind: string;
  title?: string | null;
  workspace_id?: string | null;
  agent_id?: string | null;
  pinned?: boolean;
  starred?: boolean;
  created_at?: string;
  updated_at?: string;
  [k: string]: unknown;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit?: number;
  offset?: number;
  [k: string]: unknown;
}

export interface Message {
  id: string;
  role: string;
  content: unknown;
  payload?: Partial<MediaPayload> | null;
  created_at?: string;
  [k: string]: unknown;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "blocked";

export interface Job {
  job_id: string;
  status: JobStatus | (string & {});
  output_url?: string | null;
  output?: unknown;
  error?: string | null;
  [k: string]: unknown;
}

export interface OCRResult {
  job_id?: string;
  status: string;
  type: string;
  text: string;
  pages?: number;
  confidence?: number;
  structured_data?: Record<string, unknown>;
  risk_score?: number;
  risk_level?: string;
  [k: string]: unknown;
}

export type KnowledgeStatus = "processing" | "processed" | "failed";

export interface KnowledgeItem {
  id: string;
  title: string;
  description?: string | null;
  status: KnowledgeStatus | (string & {});
  kind?: string;
  tags?: string[];
  chunks?: number;
  tokens?: number;
  file_size?: number | null;
  error_msg?: string | null;
  created_at?: string;
  [k: string]: unknown;
}

export interface KnowledgeAnswer {
  success?: boolean;
  answer: string;
  citations: Array<{ item_id: string; title: string; score: number; excerpt: string }>;
  usage?: Usage;
  metadata?: { retrieved_items: number; passages: number; model: string; latency_ms: number };
  [k: string]: unknown;
}

export interface ArchiveUnitInput {
  title?: string;
  summary?: string;
  content?: string;
  category?: string;
  engine_scope?: string;
  signals?: unknown;
  confidence?: number;
  source?: string;
  sensitivity?: string;
}

export interface ArchiveUnit extends ArchiveUnitInput {
  id: string;
  owner_type: string;
  owner_id: string;
  created_at: string;
  [k: string]: unknown;
}

export interface ArchiveList {
  data: ArchiveUnit[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface ApiKey {
  id: number;
  /** Only present in the create response. */
  key?: string;
  name?: string | null;
  active?: boolean;
  revoked?: boolean;
  created_at?: string;
  [k: string]: unknown;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface VoiceEvent {
  type: "user_text" | "status" | "text_delta" | "audio_chunk_ready" | "done" | "error" | (string & {});
  [k: string]: any;
}

export interface ModelInfo {
  id: string;
  public_name: string;
  product_key: string;
  type?: string;
  description?: string | null;
  context_window?: number | null;
  generation?: { gen: number; label: string };
  [k: string]: unknown;
}

export type JSONObject = Record<string, any>;
