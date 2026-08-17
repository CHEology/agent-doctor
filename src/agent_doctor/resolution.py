"""Reference, configuration-precedence, and applicability resolution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .inventory import SourceCandidate
from .parser import ParsedSource
from .privacy import is_within, redact_secrets


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
BACKTICK_PATH = re.compile(r"`([^`]*(?:references|scripts|assets)/[^`]+)`", re.IGNORECASE)
REFERENCE_KEY = re.compile(r"(?im)^\s*(?:reference|resource)\s*:\s*([^\s#]+)")
REQUIRED_SCHEMA = re.compile(r"(?im)^\s*required_policy_schema\s*:\s*['\"]?([A-Za-z0-9_.-]+)")
TARGET_SCHEMA = re.compile(r"(?im)^\s*schema\s*:\s*['\"]?([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class ReferenceDeclaration:
    raw: str
    line: int
    required: bool
    source_ref: str


@dataclass(frozen=True)
class ReferenceResolution:
    declaration: ReferenceDeclaration
    status: str
    normalized_target: str | None
    target_path: Path | None
    reason: str
    outside_read_attempted: bool
    evidence_basis: str


def extract_references(source_ref: str, content: str) -> tuple[ReferenceDeclaration, ...]:
    declarations: dict[tuple[str, int], ReferenceDeclaration] = {}
    for line_number, line in enumerate(content.splitlines(), start=1):
        required = bool(re.search(r"\b(read|required|must|before|reference)\b", line, re.IGNORECASE))
        for pattern in (MARKDOWN_LINK, BACKTICK_PATH, REFERENCE_KEY):
            for match in pattern.finditer(line):
                raw = match.group(1).strip().strip('"\'')
                if raw.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                declarations[(raw, line_number)] = ReferenceDeclaration(raw, line_number, required, source_ref)
    return tuple(declarations[key] for key in sorted(declarations, key=lambda item: (item[1], item[0])))


def _expand_supported_variables(raw: str, variables: dict[str, str]) -> tuple[str | None, str | None]:
    if raw.startswith("~"):
        return None, "home-directory shorthand is not supported by the selected profile"
    if re.search(r"%[A-Za-z_][A-Za-z0-9_]*%", raw):
        return None, "percent-delimited variable syntax is not supported by the selected profile"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        return None, "URI reference schemes are not supported by the selected local-file profile"
    referenced = re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", raw)
    unsupported = sorted({name for name in referenced if name not in variables})
    if unsupported:
        return None, f"unsupported variable(s): {', '.join(unsupported)}"
    expanded = raw
    for name, value in variables.items():
        expanded = expanded.replace(f"${{{name}}}", value).replace(f"${name}", value)
    return expanded, None


def resolve_reference(
    declaration: ReferenceDeclaration,
    *,
    declaring_path: Path,
    allowed_root: Path,
    display_root: Path,
    variables: dict[str, str] | None = None,
    case_sensitive: bool | None = None,
) -> ReferenceResolution:
    expanded, variable_error = _expand_supported_variables(declaration.raw, variables or {})
    if variable_error:
        return ReferenceResolution(
            declaration,
            "unsupported",
            None,
            None,
            variable_error,
            False,
            "profile does not define the variable form",
        )
    assert expanded is not None
    candidate = Path(expanded)
    if candidate.is_absolute():
        lexical = Path(os.path.normpath(str(candidate)))
    else:
        lexical = Path(os.path.normpath(str(declaring_path.parent / candidate)))
    # Lexical escape is decided before opening or resolving an outside target.
    lexical_root = Path(os.path.abspath(allowed_root))
    lexical_absolute = Path(os.path.abspath(lexical))
    try:
        lexical_absolute.relative_to(lexical_root)
    except ValueError:
        return ReferenceResolution(
            declaration,
            "escape",
            _display_target(lexical_absolute, display_root),
            None,
            "normalized target leaves the declaring source's allowed root",
            False,
            "lexical path normalization",
        )
    try:
        physical = lexical_absolute.resolve(strict=False)
    except OSError as exc:
        return ReferenceResolution(declaration, "error", None, None, f"path resolution failed: {exc.__class__.__name__}", False, "filesystem metadata")
    if not is_within(physical, allowed_root):
        return ReferenceResolution(
            declaration,
            "escape",
            _display_target(lexical_absolute, display_root),
            None,
            "symlink-resolved target leaves the declaring source's allowed root",
            False,
            "path identity metadata",
        )
    normalized = _display_target(lexical_absolute, display_root)
    try:
        if case_sensitive is False and not lexical_absolute.exists() and lexical_absolute.parent.is_dir():
            matches = [
                item
                for item in lexical_absolute.parent.iterdir()
                if item.name.casefold() == lexical_absolute.name.casefold()
            ]
            if len(matches) == 1:
                lexical_absolute = matches[0]
                physical = lexical_absolute.resolve(strict=False)
                if not is_within(physical, allowed_root):
                    return ReferenceResolution(
                        declaration,
                        "escape",
                        normalized,
                        None,
                        "case-insensitive target resolves outside the declaring source's allowed root",
                        False,
                        "case-insensitive directory metadata",
                    )
                normalized = _display_target(lexical_absolute, display_root)
        exists = lexical_absolute.exists()
        if not exists:
            return ReferenceResolution(declaration, "missing", normalized, lexical_absolute, "target does not exist", False, "filesystem existence metadata")
        if not lexical_absolute.is_file():
            return ReferenceResolution(declaration, "unsupported_type", normalized, lexical_absolute, "target is not a regular file", False, "filesystem type metadata")
        if case_sensitive:
            parent_names = {item.name for item in lexical_absolute.parent.iterdir()}
            if lexical_absolute.name not in parent_names:
                return ReferenceResolution(declaration, "missing", normalized, lexical_absolute, "target case does not match under the selected filesystem profile", False, "case-sensitive directory metadata")
        if not os.access(lexical_absolute, os.R_OK):
            return ReferenceResolution(declaration, "unreadable", normalized, lexical_absolute, "target is unreadable", False, "filesystem access metadata")
    except PermissionError:
        return ReferenceResolution(declaration, "error", normalized, lexical_absolute, "metadata access denied", False, "filesystem metadata")
    except OSError as exc:
        return ReferenceResolution(declaration, "error", normalized, lexical_absolute, f"metadata I/O failed: {exc.__class__.__name__}", False, "filesystem metadata")
    return ReferenceResolution(declaration, "valid", normalized, lexical_absolute, "supported relative reference resolves inside scope", False, "profile resolver plus filesystem metadata")


def _display_target(path: Path, workspace: Path) -> str:
    try:
        display = "workspace://" + path.resolve(strict=False).relative_to(workspace.resolve(strict=False)).as_posix()
        return redact_secrets(display).text
    except ValueError:
        # Do not expose an absolute outside path; retain only a lexical marker.
        return redact_secrets("outside://" + PurePosixPath(path.name).as_posix()).text


def explicit_version_mismatch(source_content: str, target_content: str) -> tuple[bool, str | None]:
    required = REQUIRED_SCHEMA.search(source_content)
    actual = TARGET_SCHEMA.search(target_content)
    if not required or not actual:
        return False, None
    required_value, actual_value = required.group(1), actual.group(1)
    explicit_incompatibility = re.search(
        rf"not\s+compatible\s+with\s+schema\s+{re.escape(required_value)}\b",
        target_content,
        re.IGNORECASE,
    )
    if actual_value != required_value and explicit_incompatibility:
        return True, f"target schema {actual_value} explicitly rejects required schema {required_value}"
    return False, None


@dataclass(frozen=True)
class ConfigValue:
    key: str
    value: Any
    source_ref: str
    layer: str
    order: int
    applicability: str


def flatten_config(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_config(value[key], path))
    else:
        flattened[prefix] = value
    return flattened


def resolve_config_precedence(
    parsed: Iterable[tuple[SourceCandidate, ParsedSource]],
) -> tuple[dict[str, ConfigValue], dict[str, list[ConfigValue]], list[str]]:
    rank = {"system": 0, "user": 1, "profile": 2, "project": 3, "cli": 4}
    winners: dict[str, ConfigValue] = {}
    all_values: dict[str, list[ConfigValue]] = {}
    unknown_keys: list[str] = []
    for source_order, (candidate, item) in enumerate(parsed):
        layer = str((candidate.effective_scope or {}).get("layer", "project"))
        applicability = str((candidate.effective_scope or {}).get("state", "unknown"))
        for key, value in flatten_config(item.metadata).items():
            entry = ConfigValue(key, value, candidate.source_id, layer, rank.get(layer, 3) * 10_000 + source_order, applicability)
            all_values.setdefault(key, []).append(entry)
            if applicability == "unknown":
                unknown_keys.append(key)
                continue
            if applicability == "inapplicable":
                continue
            previous = winners.get(key)
            if previous is None or entry.order >= previous.order:
                winners[key] = entry
    return winners, all_values, sorted(set(unknown_keys))
