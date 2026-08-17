"""Purpose-bound reading, secret minimization, and safe excerpts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .canonical import content_digest


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("synthetic_secret", re.compile(r"SYNTHETIC_SECRET_DO_NOT_SEND")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "credential_assignment",
        re.compile(
            r"(?im)^\s*[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)\s*[:=]\s*[^\s#]+"
        ),
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    categories: tuple[str, ...]
    changed: bool


def redact_secrets(text: str) -> RedactionResult:
    categories: list[str] = []
    redacted = text
    for category, pattern in SECRET_PATTERNS:
        if pattern.search(redacted):
            categories.append(category)
            redacted = pattern.sub(f"[REDACTED:{category}]", redacted)
    return RedactionResult(redacted, tuple(sorted(set(categories))), redacted != text)


def safe_revision(text: str) -> tuple[str, tuple[str, ...]]:
    filtered = redact_secrets(text)
    # A digest of a low-entropy secret can disclose it by dictionary attack. When
    # content contains a recognized secret, fingerprint only the redacted form.
    payload = filtered.text if filtered.changed else text
    return content_digest(payload), filtered.categories


def minimize_excerpt(text: str, *, limit: int = 240) -> tuple[str, tuple[str, ...], str]:
    filtered = redact_secrets(text.strip())
    excerpt = filtered.text
    disclosure = "redacted" if filtered.changed else "excerpt"
    if len(excerpt) > limit:
        excerpt = excerpt[: max(0, limit - 1)] + "…"
    return excerpt, filtered.categories, disclosure


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


@dataclass(frozen=True)
class ReadResult:
    status: str
    content: str | None
    revision: str | None
    sensitivity: tuple[str, ...]
    diagnostic: str | None
    truncated: bool = False


class SafeReader:
    """Read untrusted text without executing it or expanding its authority."""

    def __init__(self, *, max_bytes: int = 2_000_000) -> None:
        self.max_bytes = max_bytes

    def read_text(
        self,
        path: Path,
        *,
        allowed_root: Path,
        purpose: str,
        source_type: str,
        inspection: str = "allowed",
    ) -> ReadResult:
        if not is_within(path, allowed_root):
            return ReadResult("denied", None, None, (), "path is outside the frozen inspection root")
        if source_type == "script" or inspection == "metadata_only":
            return ReadResult("withheld", None, None, ("executable",), "script/resource content is metadata-only")
        if inspection == "withheld":
            return ReadResult("withheld", None, None, (), f"content is withheld for purpose {purpose}")
        try:
            stat_before = path.stat()
            if not path.is_file():
                return ReadResult("missing", None, None, (), "target is missing or not a regular file")
            with path.open("rb") as handle:
                raw = handle.read(self.max_bytes + 1)
            stat_after = path.stat()
        except FileNotFoundError:
            return ReadResult("missing", None, None, (), "file does not exist")
        except PermissionError:
            return ReadResult("unreadable", None, None, (), "permission denied")
        except OSError as exc:
            return ReadResult("error", None, None, (), f"I/O failure: {exc.__class__.__name__}")
        identity_before = (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns)
        identity_after = (stat_after.st_dev, stat_after.st_ino, stat_after.st_size, stat_after.st_mtime_ns)
        if identity_before != identity_after:
            return ReadResult("error", None, None, (), "path identity or revision changed during read")
        truncated = len(raw) > self.max_bytes
        raw = raw[: self.max_bytes]
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            if truncated and exc.end == len(raw) and exc.reason == "unexpected end of data":
                # A byte bound can bisect the final Unicode scalar. Retain the
                # complete prefix as partial evidence instead of retyping a
                # valid UTF-8 source as malformed.
                content = raw[: exc.start].decode("utf-8")
            else:
                return ReadResult("error", None, None, (), "content is not valid UTF-8")
        revision, sensitivity = safe_revision(content)
        if truncated:
            return ReadResult(
                "partial",
                content,
                revision,
                sensitivity,
                f"content exceeded the {self.max_bytes}-byte parser limit",
                True,
            )
        return ReadResult("read", content, revision, sensitivity, None)


def effective_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"
