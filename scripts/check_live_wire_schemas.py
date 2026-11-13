"""Compare deployed public wire schemas against a pinned public NeoMundi source.

Read-only HTTPS GETs, no API credentials, observation calls, provider calls,
production changes, or retries. Explicit command only; never called in CI.
"""
from __future__ import annotations

import hashlib
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOURCE_COMMIT = "43482c070364dde9830e51aa227b8c8627c48249"
LIVE_BASE = "https://api.neomundi.io/v1/contracts/"
PINNED_BASE = (
    "https://raw.githubusercontent.com/neomundi-io/neomundi-measurement-mcp/"
    + SOURCE_COMMIT + "/runtime/schemas/contracts/"
)
FILES = ("govern-rest-1.0.json", "govern-sse-1.0.json")
LIMIT = 1_000_000


def fetch(url: str) -> bytes:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "neomundi-sdk-schema-audit/1"})
    with urlopen(req, timeout=15) as response:
        if response.status != 200:
            raise ValueError("HTTP response was not 200")
        content = response.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise ValueError("Schema exceeds size limit")
    obj = json.loads(content)
    if not isinstance(obj, dict) or obj.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("Not the expected JSON Schema draft")
    return content


def main() -> int:
    failed = False
    for name in FILES:
        try:
            live = fetch(LIVE_BASE + name)
            pinned = fetch(PINNED_BASE + name)
            match = live == pinned
            print(name, "BYTE_MATCH" if match else "BYTE_MISMATCH")
            print("  live SHA256:", hashlib.sha256(live).hexdigest())
            print("  pinned SHA256:", hashlib.sha256(pinned).hexdigest())
            if not match:
                failed = True
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            # No response bytes and no traces or credentials displayed.
            print(name, "UNVERIFIED:", type(exc).__name__)
            failed = True
    if failed:
        print("STOP: schema parity not established; do not claim 3.5.0 verified")
        return 1
    print("PASS: both deployed schema documents byte-match the pinned public source")
    print("This proves schema parity only, not scientific comparability or all runtime paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
