/**
 * Errors raised by the OpenQCore client.
 *
 * Every API error uses one envelope:
 *   { "success": false, "error": { "code", "message", "trace_id", "extra" } }
 * `APIStatusError` exposes those fields and a subclass is picked from the
 * HTTP status, so you can `catch` exactly what you care about.
 */

export class OpenQCoreError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class APIError extends OpenQCoreError {}

export class APIConnectionError extends APIError {
  readonly cause?: unknown;
  constructor(message = "Connection error.", cause?: unknown) {
    super(message);
    this.cause = cause;
  }
}

export class APITimeoutError extends APIConnectionError {
  constructor() {
    super("Request timed out.");
  }
}

export class APIUserAbortError extends APIError {
  constructor() {
    super("Request was aborted.");
  }
}

export class StreamError extends APIError {}

export class APIStatusError extends APIError {
  readonly status: number;
  readonly code: string | null;
  readonly traceId: string | null;
  readonly extra: Record<string, unknown>;
  readonly headers: Headers;
  readonly body: unknown;

  constructor(
    status: number,
    message: string,
    opts: { code?: string | null; traceId?: string | null; extra?: Record<string, unknown>; headers: Headers; body?: unknown },
  ) {
    const parts = [String(status)];
    if (opts.code) parts.push(opts.code);
    parts.push(message);
    super(parts.join(" ") + (opts.traceId ? ` (trace_id=${opts.traceId})` : ""));
    this.status = status;
    this.code = opts.code ?? null;
    this.traceId = opts.traceId ?? null;
    this.extra = opts.extra ?? {};
    this.headers = opts.headers;
    this.body = opts.body;
  }
}

/** 400 */
export class BadRequestError extends APIStatusError {}
/** 401: missing, expired or invalid credentials. */
export class AuthenticationError extends APIStatusError {}
/** 402: wallet balance or free quota used up (WALLET_EXHAUSTED). */
export class InsufficientBalanceError extends APIStatusError {}
/** 403 */
export class PermissionDeniedError extends APIStatusError {}
/** 404: does not exist or is not yours. */
export class NotFoundError extends APIStatusError {}
/** 409: the same request is already running, or request_id was reused. */
export class ConflictError extends APIStatusError {}
/** 410: deleted. */
export class GoneError extends APIStatusError {}
/** 413 */
export class PayloadTooLargeError extends APIStatusError {}
/** 415 */
export class UnsupportedMediaTypeError extends APIStatusError {}
/** 422: validation failed; field errors are in `details`. */
export class UnprocessableEntityError extends APIStatusError {
  get details(): unknown {
    return this.extra["details"];
  }
}
/** 429: `retryAfter` is in seconds when the server sent it. */
export class RateLimitError extends APIStatusError {
  get retryAfter(): number | null {
    const v = this.headers.get("retry-after");
    const n = v == null ? NaN : Number(v);
    return Number.isFinite(n) ? n : null;
  }
}
/** 5xx */
export class InternalServerError extends APIStatusError {}
/** 503: overloaded or a provider is unavailable. */
export class ServiceUnavailableError extends InternalServerError {}
/** 504: the model did not answer in time. */
export class GatewayTimeoutError extends InternalServerError {}

const STATUS_MAP: Record<number, typeof APIStatusError> = {
  400: BadRequestError,
  401: AuthenticationError,
  402: InsufficientBalanceError,
  403: PermissionDeniedError,
  404: NotFoundError,
  409: ConflictError,
  410: GoneError,
  413: PayloadTooLargeError,
  415: UnsupportedMediaTypeError,
  422: UnprocessableEntityError,
  429: RateLimitError,
  503: ServiceUnavailableError,
  504: GatewayTimeoutError,
};

export function errorFromResponse(status: number, headers: Headers, rawText: string): APIStatusError {
  let body: unknown = rawText || undefined;
  try {
    body = rawText ? JSON.parse(rawText) : undefined;
  } catch {
    /* plain text body */
  }

  let code: string | null = null;
  let message: string | null = null;
  let traceId: string | null = null;
  let extra: Record<string, unknown> = {};

  if (body && typeof body === "object") {
    const b = body as Record<string, any>;
    if (b.error && typeof b.error === "object") {
      code = b.error.code ?? null;
      message = b.error.message ?? null;
      traceId = b.error.trace_id ?? null;
      extra = b.error.extra ?? {};
    } else if ("detail" in b) {
      const d = b.detail;
      if (typeof d === "string") message = d;
      else if (d && typeof d === "object" && !Array.isArray(d)) {
        code = d.code ?? null;
        message = d.message ?? d.detail ?? null;
      } else extra = { details: d };
    }
  } else if (typeof body === "string" && body.trim()) {
    message = body.trim().slice(0, 500);
  }

  traceId = traceId ?? headers.get("x-trace-id") ?? headers.get("x-request-id");
  const Cls = STATUS_MAP[status] ?? (status >= 500 ? InternalServerError : APIStatusError);
  return new Cls(status, message ?? "Request failed.", { code, traceId, extra, headers, body });
}
