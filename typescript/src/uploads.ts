/** Normalise the ways a caller can pass a file into a Blob + filename. */

export type FileLike =
  | Blob
  | ArrayBuffer
  | ArrayBufferView
  | { data: Blob | ArrayBuffer | ArrayBufferView; filename: string; contentType?: string }
  /** A path on disk (Node.js only). */
  | string;

const TYPES: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  txt: "text/plain",
  md: "text/markdown",
  markdown: "text/markdown",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  wav: "audio/wav",
  mp3: "audio/mpeg",
  m4a: "audio/mp4",
  webm: "audio/webm",
  ogg: "audio/ogg",
  opus: "audio/ogg",
};

function guessType(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return TYPES[ext] ?? "application/octet-stream";
}

function basename(p: string): string {
  return p.split(/[\\/]/).pop() || p;
}

export async function toUpload(
  file: FileLike,
  opts: { defaultName: string; forceTypePrefix?: string },
): Promise<{ blob: Blob; filename: string }> {
  let data: Blob | ArrayBuffer | ArrayBufferView;
  let filename: string;
  let type: string | undefined;

  if (typeof file === "string") {
    const fs = await import("node:fs/promises").catch(() => {
      throw new TypeError("Passing a file path only works in Node.js. Pass a Blob, File or bytes instead.");
    });
    data = await fs.readFile(file);
    filename = basename(file);
  } else if (typeof Blob !== "undefined" && file instanceof Blob) {
    data = file;
    filename = (file as any).name || opts.defaultName;
    type = file.type || undefined;
  } else if (file instanceof ArrayBuffer || ArrayBuffer.isView(file)) {
    data = file;
    filename = opts.defaultName;
  } else if (file && typeof file === "object" && "data" in file) {
    data = file.data;
    filename = file.filename;
    type = file.contentType;
  } else {
    throw new TypeError("file must be a Blob/File, bytes, { data, filename }, or a path (Node.js).");
  }

  type = type || guessType(filename);
  if (opts.forceTypePrefix && !type.startsWith(opts.forceTypePrefix)) {
    const ext = filename.includes(".") ? filename.split(".").pop()!.toLowerCase() : "octet-stream";
    type = opts.forceTypePrefix + ext;
  }

  const blob =
    data instanceof Blob && data.type === type ? data : new Blob([data as BlobPart], { type });
  return { blob, filename };
}
