"""Canonical serialization and stable, secret-safe identifiers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import PurePath
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: canonical_json(item))
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return value

def canonical_json(value: Any) -> str:
    """Return the sole serialization used for digests and stable comparisons."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def content_digest(content: bytes | str) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    hexadecimal = digest(value).split(":", 1)[1]
    return f"{prefix}-{hexadecimal[:length]}"


def strip_volatile(value: Any, volatile_keys: Sequence[str] = ("run_id", "started_at", "completed_at")) -> Any:
    """Remove only declared volatile fields for reproducibility comparisons."""

    volatile = set(volatile_keys)
    if isinstance(value, Mapping):
        return {
            key: strip_volatile(item, volatile_keys)
            for key, item in value.items()
            if key not in volatile
        }
    if isinstance(value, list):
        return [strip_volatile(item, volatile_keys) for item in value]
    return value
