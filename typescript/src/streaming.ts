import { StreamError } from "./errors.js";

/**
 * A Server-Sent Events stream. Iterate it with `for await`; the connection
 * closes at the end, on `break`, or with `abort()`.
 */
export class Stream<T> implements AsyncIterable<T> {
  private consumed = false;

  constructor(
    readonly response: Response,
    private readonly controller: AbortController,
    private readonly cast: (obj: any) => T,
    private readonly opts: { doneMarker: boolean; isFinal: (obj: any) => boolean } = {
      doneMarker: true,
      isFinal: () => false,
    },
  ) {}

  async *[Symbol.asyncIterator](): AsyncIterator<T> {
    if (this.consumed) throw new Error("This stream was already consumed.");
    this.consumed = true;
    let finished = false;
    try {
      for await (const line of readLines(this.response)) {
        if (!line.startsWith("data:")) continue; // comments, event:, id:
        const data = line.slice(5).trimStart();
        if (!data) continue;
        if (data === "[DONE]") {
          finished = true;
          break;
        }
        let obj: unknown;
        try {
          obj = JSON.parse(data);
        } catch {
          continue;
        }
        if (!obj || typeof obj !== "object") continue;
        yield this.cast(obj);
        if (this.opts.isFinal(obj)) {
          finished = true;
          if (!this.opts.doneMarker) break;
        }
      }
      if (!finished) throw new StreamError("The stream ended before the server finished the response.");
    } finally {
      this.controller.abort();
    }
  }

  /** Consume the stream and return all text (chat streams). */
  async text(): Promise<string> {
    let out = "";
    for await (const item of this) {
      const c = (item as any)?.content;
      if (typeof c === "string") out += c;
    }
    return out;
  }

  /** Stop reading and close the connection. */
  abort(): void {
    this.controller.abort();
  }

  get headers(): Headers {
    return this.response.headers;
  }
}

async function* readLines(response: Response): AsyncGenerator<string> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.search(/\r\n|\r|\n/)) !== -1) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + (buffer.startsWith("\r\n", idx) ? 2 : 1));
        yield line;
      }
    }
    buffer += decoder.decode();
    if (buffer) yield buffer;
  } finally {
    reader.releaseLock();
  }
}
