"""Semantic request identity; raw credentials never participate in persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def credential_scope(key: str) -> str:
    return digest_bytes(("matrix-wan3/wavespeed/" + key).encode("utf-8"))


def request_identity(*, route: str, payload: Mapping[str, Any], media_digests: Mapping[str, Any], nonce: str, scope: str) -> str:
    frozen = {
        "provider": "wavespeed",
        "scope": scope,
        "route": route,
        "payload": payload,
        "media": media_digests,
        "nonce": nonce,
    }
    encoded = json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return digest_bytes(encoded)


def generation_intent(*, route: str, payload: Mapping[str, Any], media_digests: Mapping[str, Any], nonce: str) -> str:
    """Account/input-independent guard for one durable queued intent nonce."""
    frozen = {"provider": "wavespeed", "intent_nonce": nonce}
    encoded = json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return digest_bytes(encoded)
