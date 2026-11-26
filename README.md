# OpenQCore SDKs

Official client libraries for the [OpenQCore API](https://www.openqcore.com/docs).

| Language | Package | Install | Docs |
| --- | --- | --- | --- |
| Python 3.9+ | [`openqcore`](https://pypi.org/project/openqcore/) | `pip install openqcore` | [python/README.md](python/README.md) |
| TypeScript / JavaScript (Node 18+, Bun, Deno, Edge) | [`openqcore`](https://www.npmjs.com/package/openqcore) | `npm install openqcore` | [typescript/README.md](typescript/README.md) |

Both SDKs cover the same API: chat (with streaming), sessions and messages, voice, Iris (images, video, OCR), knowledge with cited answers, archive, API keys, models, usage, search, RAG, embeddings and ingest.

```python
from openqcore import OpenQCore

client = OpenQCore()
session = client.sessions.create()
print(client.chat.create(session_id=session.id, message="Hello").content)
```

```ts
import OpenQCore from "openqcore";

const client = new OpenQCore();
const session = await client.sessions.create();
console.log((await client.chat.create({ session_id: session.id, message: "Hello" })).content);
```

For other languages, call the REST API directly; every endpoint is in the [API reference](https://www.openqcore.com/docs/api).

## Development

```bash
# Python
cd python && pip install -e ".[dev]" && pytest && ruff check . && mypy src
python scripts/gen_async.py   # after editing resources/_sync.py

# TypeScript
cd typescript && npm install && npm test
```

## Releasing

1. Bump the version in `python/src/openqcore/_version.py` and `typescript/package.json` + `typescript/src/version.ts`, and add a `CHANGELOG.md` entry.
2. Tag `python-vX.Y.Z` or `typescript-vX.Y.Z`; the `publish` workflow builds, tests and publishes.

MIT licensed. Security issues: security@openqcore.com.
