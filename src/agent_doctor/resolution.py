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
CODE_SPAN = re.compile(r"`([^`\n]+)`")
REFERENCE_KEY = re.compile(r"(?im)^\s*(?:reference|resource)\s*:\s*([^\s#]+)")
REQUIRED_SCHEMA = re.compile(r"(?im)^\s*required_policy_schema\s*:\s*['\"]?([A-Za-z0-9_.-]+)")
TARGET_SCHEMA = re.compile(r"(?im)^\s*schema\s*:\s*['\"]?([A-Za-z0-9_.-]+)")
OPTIONAL_REFERENCE_CUE = re.compile(
    r"(?:\boptional\b|\bif\s+(?:it\s+is\s+)?(?:available|present|readable)\b|"
    r"\bwhen\s+available\b|可选|如(?:果)?可用|若(?:能读|可读|存在|可用)|"
    r"只要[^。；;\n]{0,40}(?:能读|可读|存在|可用)|"
    r"(?:想|如需|若要)[^。；;\n]{0,40}(?:看|了解|查看|确认|处理))",
    re.IGNORECASE,
)
SINGLE_FILE_FALLBACK = re.compile(
    r"(?:\bsingle[- ]file\b[^.\n]{0,80}\b(?:fallback|mode|installation)\b|"
    r"\bfallback\b[^.\n]{0,80}\bsingle[- ]file\b|"
    r"单文件[^。；;\n]{0,60}(?:兜底|退化|安装|模式)|"
    r"本文件[^。；;\n]{0,30}(?:单独|独立)[^。；;\n]{0,20}兜底|"
    r"只给(?:了)?\s*`?SKILL\.md`?[^。；;\n]{0,40}(?:兜底|退化))",
    re.IGNORECASE,
)
FALLBACK_TARGET = re.compile(
    r"(?:\.?/)?(?:references|evals)/[A-Za-z0-9._/-]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReferenceDeclaration:
    raw: str
    line: int
    required: bool
    source_ref: str
    optional: bool = False
    optional_basis: str | None = None


@dataclass(frozen=True)
class ReferenceResolution:
    declaration: ReferenceDeclaration
    status: str
    normalized_target: str | None
    target_path: Path | None
    reason: str
    outside_read_attempted: bool
    evidence_basis: str


def _local_reference_token(raw: str) -> str | None:
    """Return one local path token, never a command, placeholder, or URI.

    Reference validity is a high-precision check.  A code span containing a
    shell command (or prose which happens to mention ``scripts/``) is not a
    declaration of that entire span as one path.
    """

    token = raw.strip().strip('"\'')
    if token.startswith("<") and token.endswith(">"):
        token = token[1:-1].strip()
    if not token or any(character.isspace() for character in token):
        return None
    if any(character in token for character in ("<", ">", "[", "]", "|", ";", "&")):
        return None
    if token in {".", "..", "..."} or "..." in token:
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", token):
        return None
    # Markdown targets may carry a fragment; the fragment is not part of the
    # filesystem identity.  Query-bearing targets are not a supported local
    # file reference and are ignored rather than guessed.
    if "?" in token:
        return None
    token = token.split("#", 1)[0]
    if not token:
        return None
    if token.startswith("$") and "/" not in token:
        # Skill/tool mentions and spreadsheet formula fragments are not
        # environment-variable-backed file references.
        return None
    if token.startswith(".") and not token.startswith(("./", "../")) and "/" not in token:
        # Extension examples and CSS selectors do not identify a local target.
        return None
    path_shape = (
        token.startswith(("./", "../", "~/", "/"))
        or "/" in token
        or bool(re.search(r"^[^./][^/]*\.[A-Za-z0-9]{1,12}$", token))
    )
    return token if path_shape else None


def _code_span_has_reference_context(prefix: str) -> bool:
    """Recognize a narrow load/navigation phrase immediately before a span."""

    english = re.search(
        r"\b(?:read|load|open|consult|follow|inspect|see|reference)"
        r"(?:\s+(?:the|this|that|following|required|relevant|applicable|primary|supporting|additional|"
        r"instructions?|file|resource|reference|here|at))*[\s:,-]*$",
        prefix,
        re.IGNORECASE,
    )
    chinese = re.search(
        r"(?:读取|阅读|打开|参阅|遵循|查看|检查)(?:该|此|以下|相关|完整|主要|支持性|文件|资源|说明)*[：:\s]*$",
        prefix,
    )
    return bool(english or chinese)


def extract_references(source_ref: str, content: str) -> tuple[ReferenceDeclaration, ...]:
    declarations: dict[tuple[str, int], ReferenceDeclaration] = {}
    lines = content.splitlines()
    fallback_contracts: list[tuple[int, tuple[str, ...]]] = []
    for fallback_line, value in enumerate(lines, start=1):
        if not SINGLE_FILE_FALLBACK.search(value):
            continue
        targets = tuple(
            sorted(
                {
                    match.group(0).lstrip("./")
                    for match in FALLBACK_TARGET.finditer(value)
                }
            )
        )
        fallback_contracts.append((fallback_line, targets))

    def fallback_applies(raw: str, line_number: int) -> bool:
        normalized = raw.lstrip("./")
        if not normalized.startswith(("references/", "evals/")):
            return False
        for fallback_line, targets in fallback_contracts:
            if targets:
                if any(
                    normalized == target
                    or (target.endswith("/") and normalized.startswith(target))
                    for target in targets
                ):
                    return True
                continue
            if abs(fallback_line - line_number) <= 1:
                return True
        return False

    fence: str | None = None
    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence is not None:
            continue
        required = bool(re.search(r"\b(read|required|must|before|reference)\b", line, re.IGNORECASE))
        for pattern in (MARKDOWN_LINK, CODE_SPAN, REFERENCE_KEY):
            for match in pattern.finditer(line):
                # A Markdown link or an explicit reference/resource key
                # declares a target by syntax.  A bare code span needs an
                # action/reference cue *before* it; otherwise ordinary prose
                # such as "the `scripts/` directory is for local use" becomes
                # a false declaration.
                if pattern is CODE_SPAN:
                    if not _code_span_has_reference_context(line[: match.start()]):
                        continue
                    candidate_token = match.group(1).strip().strip('"\'')
                    # Bare names in prose may be resolved in a task-dependent
                    # runtime directory. Without explicit reference syntax,
                    # static analysis cannot anchor them to this source.
                    if "/" not in candidate_token and not candidate_token.startswith(("./", "../", "~/")):
                        continue
                    if not candidate_token.startswith(
                        ("./", "../", "references/", "resources/")
                    ):
                        # Unqualified task-output paths such as docs/, private/,
                        # tmp/, and assets/source are commonly relative to a
                        # future target workspace rather than this declaring
                        # Skill. Their base is semantically determined.
                        continue
                raw = _local_reference_token(match.group(1))
                if raw is None:
                    continue
                line_optional = bool(OPTIONAL_REFERENCE_CUE.search(line))
                fallback_optional = fallback_applies(raw, line_number)
                optional = line_optional or fallback_optional
                optional_basis = (
                    "explicit optional/availability qualifier on the declaration line"
                    if line_optional
                    else "explicit single-file fallback contract in the declaring Skill"
                    if fallback_optional
                    else None
                )
                declarations[(raw, line_number)] = ReferenceDeclaration(
                    raw,
                    line_number,
                    required,
                    source_ref,
                    optional,
                    optional_basis,
                )
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
        if lexical_absolute.is_dir():
            return ReferenceResolution(
                declaration,
                "valid_directory",
                normalized,
                lexical_absolute,
                "supported relative reference resolves to an in-scope directory",
                False,
                "profile resolver plus filesystem metadata",
            )
        if not lexical_absolute.is_file():
            return ReferenceResolution(declaration, "unsupported_type", normalized, lexical_absolute, "target is neither a regular file nor a directory", False, "filesystem type metadata")
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


def explicit_version_compatibility(
    source_content: str, target_content: str
) -> tuple[str, str]:
    """Evaluate only an explicit schema compatibility contract.

    Timestamps and undeclared notions of "latest" are intentionally ignored.
    """

    required = REQUIRED_SCHEMA.search(source_content)
    actual = TARGET_SCHEMA.search(target_content)
    if not required:
        return "no_contract", "the declaring source states no required policy schema"
    if not actual:
        return "insufficient_evidence", "the target states no schema for the declared requirement"
    required_value, actual_value = required.group(1), actual.group(1)
    if actual_value == required_value:
        return (
            "compatible",
            f"target schema {actual_value} matches required schema {required_value}",
        )
    explicit_incompatibility = re.search(
        rf"not\s+compatible\s+with\s+schema\s+{re.escape(required_value)}\b",
        target_content,
        re.IGNORECASE,
    )
    if explicit_incompatibility:
        return (
            "incompatible",
            f"target schema {actual_value} explicitly rejects required schema {required_value}",
        )
    return (
        "insufficient_evidence",
        f"target schema {actual_value} differs from required schema {required_value} without an explicit compatibility statement",
    )


def explicit_version_mismatch(source_content: str, target_content: str) -> tuple[bool, str | None]:
    status, reason = explicit_version_compatibility(source_content, target_content)
    return status == "incompatible", reason if status == "incompatible" else None


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
