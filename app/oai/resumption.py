"""Resumption tokens (OAI-PMH §3.5).

Tokens are base64url-encoded JSON — self-describing, no server-side state,
so a cPanel Passenger restart mid-harvest is safe. The token carries the
full query (metadataPrefix, set, from, until), the cursor, and the total
count so the ``<resumptionToken>`` element can echo ``completeListSize``
and ``cursor``.

Tokens are opaque to harvesters but not tamper-proof; the ``total`` in the
live response is authoritative, not the token's copy.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from .errors import OaiError

TOKEN_VERSION = 1


@dataclass(frozen=True)
class Token:
    prefix: str
    set: str | None
    from_: str | None
    until: str | None
    cursor: int
    total: int

    def to_wire(self) -> str:
        payload = {
            "v": TOKEN_VERSION,
            "prefix": self.prefix,
            "set": self.set,
            "from": self.from_,
            "until": self.until,
            "cursor": self.cursor,
            "total": self.total,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(raw: str) -> Token:
    """Parse a token or raise ``OaiError('badResumptionToken')``."""
    if not raw:
        raise OaiError("badResumptionToken", "resumptionToken is empty")
    try:
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw + pad))
    except (ValueError, json.JSONDecodeError):
        raise OaiError("badResumptionToken", "resumptionToken is malformed")
    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise OaiError("badResumptionToken", "unsupported resumptionToken version")
    prefix = payload.get("prefix")
    if not isinstance(prefix, str) or not prefix:
        raise OaiError("badResumptionToken", "resumptionToken lacks metadataPrefix")
    try:
        cursor = int(payload.get("cursor", 0))
        total = int(payload.get("total", 0))
    except (TypeError, ValueError):
        raise OaiError("badResumptionToken", "resumptionToken cursor/total invalid")
    if cursor < 0 or total < 0:
        raise OaiError("badResumptionToken", "resumptionToken cursor/total invalid")
    return Token(
        prefix=prefix,
        set=payload.get("set"),
        from_=payload.get("from"),
        until=payload.get("until"),
        cursor=cursor,
        total=total,
    )
