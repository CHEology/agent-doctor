"""Defensive parsing and qualifier-preserving normalization."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any

from .canonical import stable_id
from .model import Claim
from .privacy import minimize_excerpt


KEY_VALUE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$")
QUALIFIER_PATTERN = re.compile(r"\b(unless|except|only|when|while|if|not for)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParseDiagnostic:
    code: str
    message: str
    line: int | None
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "line": self.line, "severity": self.severity}


@dataclass(frozen=True)
class ParsedSource:
    source_ref: str
    metadata: dict[str, Any]
    claims: tuple[Claim, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
    completeness: str
    body_start_line: int


def _unquote(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        try:
            return int(value)
        except ValueError:
            pass
    return value


def parse_front_matter(content: str) -> tuple[dict[str, Any], int, list[ParseDiagnostic], str]:
    """Parse the reviewed SKILL.md top-level metadata subset without YAML execution."""

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        # Fixture and legacy sources may expose loose metadata. It is observed
        # but does not satisfy the official required-front-matter contract.
        loose_metadata: dict[str, Any] = {}
        loose_diagnostics = [ParseDiagnostic("skill.front-matter.missing", "SKILL.md has no YAML front matter", 1, "warning")]
        for line_number, line in enumerate(lines[:40], start=1):
            match = KEY_VALUE.match(line)
            if match and match.group(1).lower() in {"id", "name", "description", "mode", "reference", "required_policy_schema"}:
                raw_value = match.group(2).strip()
                if (
                    raw_value.count("[") != raw_value.count("]")
                    or raw_value.count("{") != raw_value.count("}")
                    or (raw_value.startswith(('"', "'")) and not raw_value.endswith(raw_value[0]))
                ):
                    loose_diagnostics.append(
                        ParseDiagnostic(
                            "skill.metadata.malformed-value",
                            f"unterminated metadata value for {match.group(1)}",
                            line_number,
                            "error",
                        )
                    )
                loose_metadata[match.group(1).lower()] = _unquote(raw_value)
        return loose_metadata, 1, loose_diagnostics, "partial"

    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing is None:
        return {}, 1, [ParseDiagnostic("skill.front-matter.unterminated", "YAML front matter is not terminated", 1, "error")], "partial"

    metadata: dict[str, Any] = {}
    diagnostics: list[ParseDiagnostic] = []
    index = 1
    while index < closing:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = KEY_VALUE.match(line)
        if not match:
            # Nested metadata is retained as an unsupported declaration rather
            # than guessed by the minimal parser.
            diagnostics.append(
                ParseDiagnostic("skill.front-matter.unsupported-line", "unsupported top-level metadata syntax", index + 1, "warning")
            )
            index += 1
            continue
        key, raw_value = match.group(1), match.group(2)
        if key in metadata:
            diagnostics.append(ParseDiagnostic("skill.front-matter.duplicate-key", f"duplicate metadata key: {key}", index + 1, "error"))
        stripped_value = raw_value.strip()
        if (
            stripped_value.count("[") != stripped_value.count("]")
            or stripped_value.count("{") != stripped_value.count("}")
            or (stripped_value.startswith(('"', "'")) and not stripped_value.endswith(stripped_value[0]))
        ):
            diagnostics.append(
                ParseDiagnostic(
                    "skill.front-matter.malformed-value",
                    f"unterminated metadata value for {key}",
                    index + 1,
                    "error",
                )
            )
        if raw_value.strip() in {"|", ">", "|-", ">-", "|+", ">+"}:
            folded = raw_value.strip().startswith(">")
            block_indent: int | None = None
            block: list[str] = []
            cursor = index + 1
            while cursor < closing:
                candidate = lines[cursor]
                if not candidate.strip():
                    block.append("")
                    cursor += 1
                    continue
                indent = len(candidate) - len(candidate.lstrip(" "))
                if block_indent is None:
                    block_indent = indent
                if indent < (block_indent or 0):
                    break
                block.append(candidate[(block_indent or 0) :])
                cursor += 1
            metadata[key] = " ".join(part.strip() for part in block).strip() if folded else "\n".join(block).rstrip()
            index = cursor
            continue
        metadata[key] = _unquote(raw_value)
        index += 1
    return metadata, closing + 2, diagnostics, "complete" if not any(item.severity == "error" for item in diagnostics) else "partial"


def _line_span(content: str, line_number: int, line: str) -> dict[str, int]:
    physical = content.splitlines(keepends=True)
    prefix = "".join(physical[: line_number - 1])
    start_byte = len(prefix.encode("utf-8"))
    line_bytes = len(line.encode("utf-8"))
    return {
        "start_line": line_number,
        "end_line": line_number,
        "start_column": 1,
        "end_column": max(1, len(line)),
        "start_byte": start_byte,
        "end_byte": start_byte + line_bytes,
    }


def _modality(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\b(do not|must not|never|forbid|prohibit)\b", lowered):
        return "forbidden"
    if re.search(r"\b(must|required|always|shall|before responding|before review)\b", lowered):
        return "required"
    if re.search(r"\b(should|prefer|recommended)\b", lowered):
        return "preferred"
    if re.search(r"\b(may|can|optional)\b", lowered):
        return "permitted"
    return "declarative"


def _dimensions(text: str) -> list[tuple[str, str]]:
    lowered = text.casefold()
    dimensions: list[tuple[str, str]] = []
    if re.search(r"\b(reference|read [`\w./${}-]+|references?/|scripts?/|assets?/)\b", lowered):
        dimensions.append(("reference", "reference_validity"))
    if re.search(r"\b(description|trigger|use for|handles?|primary handler|applicable)\b", lowered):
        dimensions.append(("trigger", "trigger"))
    if re.search(r"\b(output|format|start with|end with|sources section|json|yaml|markdown|risk summary)\b", lowered):
        dimensions.append(("output_constraint", "output_form"))
    if re.search(r"\b(ask|question|questions|without questions|without asking)\b", lowered):
        dimensions.append(("question_policy", "question_policy"))
    if re.search(r"\b(run|edit|action|return|verify|extract|review|create|preserve|apply|write)\b", lowered):
        dimensions.append(("action", "required_action"))
    if re.search(r"\b(subtree|under [\w./-]+|scope|directory|path)\b", lowered):
        dimensions.append(("scope", "applicability"))
    if not dimensions:
        dimensions.append(("statement", "general"))
    # Keep order, but never duplicate a dimension for one source line.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for kind, dimension in dimensions:
        if dimension in seen:
            continue
        seen.add(dimension)
        unique.append((kind, dimension))
    return unique


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _qualifiers(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0).casefold() for match in QUALIFIER_PATTERN.finditer(text)))


def _claims_from_lines(source_ref: str, content: str, *, first_line: int = 1, completeness: str = "complete") -> list[Claim]:
    claims: list[Claim] = []
    lines = content.splitlines()
    for offset, line in enumerate(lines[first_line - 1 :], start=first_line):
        if not line.strip() or line.lstrip().startswith(("#", "<!--")):
            continue
        excerpt, _, _ = minimize_excerpt(line, limit=400)
        normalized = _normalize_text(excerpt)
        qualifiers = _qualifiers(excerpt)
        modality = _modality(excerpt)
        span = _line_span(content, offset, line)
        for kind, dimension in _dimensions(excerpt):
            identity = {
                "source": source_ref,
                "kind": kind,
                "dimension": dimension,
                "modality": modality,
                "normalized": normalized,
                "span": span,
            }
            claims.append(
                Claim(
                    claim_id=stable_id("claim", identity),
                    source_ref=source_ref,
                    kind=kind,
                    dimension=dimension,
                    modality=modality,
                    normalized=normalized,
                    excerpt=excerpt,
                    qualifiers=qualifiers,
                    span=span,
                    completeness=completeness,
                )
            )
    return claims


def _flatten_toml(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    flattened: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.extend(_flatten_toml(value[key], path))
    elif isinstance(value, list):
        flattened.append((prefix, value))
    else:
        flattened.append((prefix, value))
    return flattened


def parse_config(source_ref: str, content: str) -> ParsedSource:
    try:
        metadata = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        diagnostic = ParseDiagnostic("config.toml.invalid", str(exc).split(" (at line", 1)[0], getattr(exc, "lineno", None), "error")
        return ParsedSource(source_ref, {}, (), (diagnostic,), "partial", 1)
    claims: list[Claim] = []
    for key, value in _flatten_toml(metadata):
        safe_key, _, _ = minimize_excerpt(key, limit=200)
        raw_normalized = f"{safe_key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        normalized, _, _ = minimize_excerpt(raw_normalized, limit=400)
        identity = {"source": source_ref, "kind": "configuration", "normalized": normalized}
        claims.append(
            Claim(
                claim_id=stable_id("claim", identity),
                source_ref=source_ref,
                kind="configuration",
                dimension=f"configuration:{safe_key}",
                modality="declarative",
                normalized=normalized,
                excerpt=normalized,
                qualifiers=(),
                span={"start_line": 1, "end_line": 1, "start_column": 1, "end_column": 1, "start_byte": 0, "end_byte": 0},
            )
        )
    return ParsedSource(source_ref, metadata, tuple(claims), (), "complete", 1)


def parse_source(source_ref: str, source_type: str, content: str) -> ParsedSource:
    if source_type == "config":
        return parse_config(source_ref, content)
    if source_type in {"skill_body", "skill_manifest"}:
        metadata, body_start, diagnostics, completeness = parse_front_matter(content)
        claims = _claims_from_lines(source_ref, content, first_line=body_start, completeness=completeness)
        description = metadata.get("description")
        if isinstance(description, str) and description.strip():
            excerpt, _, _ = minimize_excerpt(description, limit=400)
            identity = {"source": source_ref, "kind": "trigger", "description": _normalize_text(excerpt)}
            claims.insert(
                0,
                Claim(
                    claim_id=stable_id("claim", identity),
                    source_ref=source_ref,
                    kind="trigger",
                    dimension="trigger",
                    modality="declarative",
                    normalized=_normalize_text(excerpt),
                    excerpt=excerpt,
                    qualifiers=_qualifiers(excerpt),
                    span={"start_line": 1, "end_line": max(1, body_start - 1), "start_column": 1, "end_column": 1, "start_byte": 0, "end_byte": 0},
                    completeness=completeness,
                ),
            )
        return ParsedSource(source_ref, metadata, tuple(claims), tuple(diagnostics), completeness, body_start)
    return ParsedSource(source_ref, {}, tuple(_claims_from_lines(source_ref, content)), (), "complete", 1)
