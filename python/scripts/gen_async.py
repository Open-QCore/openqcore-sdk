"""Generate resources/_async.py from resources/_sync.py.

Run from the python/ folder:  python scripts/gen_async.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "openqcore" / "resources"

HEADER = '''"""Asynchronous resources.

GENERATED from `_sync.py` by ``scripts/gen_async.py`` — do not edit by hand.
"""
'''

RULES = [
    (r'^"""Synchronous resources\..*?"""\n', HEADER, re.S),
    (r"^import time$", "import asyncio\nimport time", re.M),
    (r"from \.\._streaming import Stream$", "from .._streaming import AsyncStream", re.M),
    (r"\bStream\[", "AsyncStream[", 0),
    (r"from \.\._client import OpenQCore$", "from .._client import AsyncOpenQCore", re.M),
    (r'client: "OpenQCore"', 'client: "AsyncOpenQCore"', 0),
    (r"^(\s*)def (?!__init__)", r"\1async def ", re.M),
    (r"return self\._client\._execute\(", "return await self._client._execute(", 0),
    (r"return self\._run\(", "return await self._run(", 0),
    (r"return _wait_for_job\(", "return await _wait_for_job(", 0),
    (r"time\.sleep\(", "await asyncio.sleep(", 0),
    (r"job = get\(job_id\)", "job = await get(job_id)", 0),
    (r"item = self\.retrieve\(", "item = await self.retrieve(", 0),
]


def generate() -> str:
    text = (ROOT / "_sync.py").read_text(encoding="utf-8")
    for pattern, repl, flags in RULES:
        text = re.sub(pattern, repl, text, flags=flags)
    return text


if __name__ == "__main__":
    out = generate()
    target = ROOT / "_async.py"
    if "--check" in sys.argv:
        sys.exit(0 if target.read_text(encoding="utf-8") == out else 1)
    target.write_text(out, encoding="utf-8")
    print(f"wrote {target}")
