"""Turn the many ways a caller can pass a file into one httpx multipart tuple."""

from __future__ import annotations

import io
import mimetypes
import os
from pathlib import Path
from typing import IO, Optional, Tuple, Union

FileContent = Union[bytes, IO[bytes]]
FileInput = Union[
    str,
    "os.PathLike[str]",
    bytes,
    IO[bytes],
    Tuple[str, FileContent],
    Tuple[str, FileContent, str],
]

_EXTRA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


def guess_type(filename: str, default: str = "application/octet-stream") -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _EXTRA_TYPES:
        return _EXTRA_TYPES[ext]
    return mimetypes.guess_type(filename)[0] or default


def to_upload(
    file: FileInput,
    *,
    default_name: str = "upload",
    force_type_prefix: Optional[str] = None,
) -> Tuple[str, bytes, str]:
    """Return ``(filename, content, content_type)``.

    ``force_type_prefix`` (e.g. ``"audio/"``) replaces a guessed type that
    does not start with it; the voice endpoints reject non-audio parts.
    """
    filename: str
    content: bytes
    content_type: Optional[str] = None

    if isinstance(file, tuple):
        if len(file) == 3:
            filename, raw, content_type = file  # type: ignore[misc]
        else:
            filename, raw = file  # type: ignore[misc]
        content = raw if isinstance(raw, bytes) else raw.read()
    elif isinstance(file, (str, os.PathLike)):
        path = Path(file)
        filename = path.name
        content = path.read_bytes()
    elif isinstance(file, bytes):
        filename = default_name
        content = file
    elif hasattr(file, "read"):
        filename = os.path.basename(getattr(file, "name", "") or default_name)
        data = file.read()
        content = data.encode() if isinstance(data, str) else data
    else:
        raise TypeError("file must be a path, bytes, a binary file object, or a (filename, content[, content_type]) tuple")

    content_type = content_type or guess_type(filename)
    if force_type_prefix and not content_type.startswith(force_type_prefix):
        ext = os.path.splitext(filename)[1].lstrip(".").lower()
        content_type = force_type_prefix + (ext or "octet-stream")
    return filename, content, content_type


def is_readable(obj: object) -> bool:
    return isinstance(obj, (io.IOBase,)) or hasattr(obj, "read")
