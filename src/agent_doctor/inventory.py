"""Codex-profile-driven discovery and complete source inventory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .canonical import stable_id
from .model import SourceRecord
from .privacy import is_within, redact_secrets
from .scope import ResolvedScope
from .types import SourceStatus, SourceType


@dataclass(frozen=True)
class SourceCandidate:
    source_id: str
    path: Path | None
    source_type: str
    location: str
    status: str
    status_reason: str
    allowed_root: Path | None
    inspection: str = "allowed"
    semantic_disclosure: str = "withheld"
    effective_scope: dict | None = None
    revision: str | None = None
    readability: str = "unknown"
    sensitivity: tuple[str, ...] = ()
    provenance: dict | None = None

    def with_read(self, *, status: str, revision: str | None, readability: str, sensitivity: tuple[str, ...], reason: str) -> "SourceCandidate":
        return replace(
            self,
            status=status,
            revision=revision,
            readability=readability,
            sensitivity=sensitivity,
            status_reason=reason,
        )

    def to_record(self) -> SourceRecord:
        return SourceRecord(
            source_id=self.source_id,
            source_type=self.source_type,
            location=self.location,
            status=self.status,
            revision=self.revision,
            readability=self.readability,
            declared_scope={"location": self.location},
            effective_scope=self.effective_scope or {"state": "unknown"},
            sensitivity=self.sensitivity,
            provenance=self.provenance or {},
            status_reason=self.status_reason,
        )


def _candidate(
    scope: ResolvedScope,
    path: Path | None,
    source_type: str,
    *,
    status: str,
    reason: str,
    allowed_root: Path | None,
    inspection: str = "allowed",
    semantic_disclosure: str = "withheld",
    effective_scope: dict | None = None,
    location: str | None = None,
    provenance: dict | None = None,
) -> SourceCandidate:
    display = location or (scope.display_location(path) if path is not None else "unknown://")
    source_id = stable_id("source", {"type": source_type, "location": display})
    return SourceCandidate(
        source_id=source_id,
        path=path,
        source_type=source_type,
        location=display,
        status=status,
        status_reason=reason,
        allowed_root=allowed_root,
        inspection=inspection,
        semantic_disclosure=semantic_disclosure,
        effective_scope=effective_scope,
        provenance=provenance,
    )


def _path_chain(root: Path, selected: Path) -> list[Path]:
    relative = selected.relative_to(root)
    chain = [root]
    current = root
    for part in relative.parts:
        current = current / part
        chain.append(current)
    return chain


def _discover_instruction_level(
    scope: ResolvedScope,
    directory: Path,
    *,
    allowed_root: Path,
    global_level: bool = False,
) -> list[SourceCandidate]:
    override = directory / "AGENTS.override.md"
    base = directory / "AGENTS.md"
    present = [path for path in (override, base) if path.exists()]
    if not present:
        return []
    selected: Path | None = None
    for path in (override, base):
        try:
            if path.is_file() and path.stat().st_size > 0:
                selected = path
                break
        except OSError:
            # The candidate is still retained below.  The bounded reader owns
            # the check lifecycle and will record an honest read error.
            selected = path
            break
    candidates: list[SourceCandidate] = []
    for path in present:
        chosen = path == selected
        candidates.append(
            _candidate(
                scope,
                path,
                SourceType.OVERRIDE.value if path.name.endswith("override.md") else SourceType.INSTRUCTION.value,
                status=SourceStatus.DISCOVERED.value if chosen else SourceStatus.SHADOWED.value,
                reason=(
                    "selected by global override/base rule"
                    if chosen and global_level
                    else "selected in project instruction chain"
                    if chosen
                    else "another non-empty instruction file was selected at this level"
                ),
                allowed_root=allowed_root,
                semantic_disclosure="withheld",
                effective_scope={"state": "applicable", "directory": scope.display_location(directory)},
            )
        )
    return candidates


def _discover_skill_root(
    scope: ResolvedScope,
    root: Path,
    *,
    allowed_root: Path,
    scope_kind: str,
) -> list[SourceCandidate]:
    if not root.exists() or not root.is_dir():
        return []
    candidates: list[SourceCandidate] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except PermissionError:
        return [
            _candidate(
                scope,
                root,
                SourceType.OTHER.value,
                status=SourceStatus.UNREADABLE.value,
                reason="skill discovery root is unreadable",
                allowed_root=allowed_root,
                inspection="metadata_only",
            )
        ]
    for ordinal, entry in enumerate(entries, start=1):
        skill_file = entry / "SKILL.md"
        resolved_entry = entry.resolve(strict=False)
        skill_allowed_root = resolved_entry
        try:
            raw_logical_location = scope.display_location(root) + "/" + entry.name + "/SKILL.md"
            location_redaction = redact_secrets(raw_logical_location)
            logical_location = location_redaction.text
            if location_redaction.changed:
                logical_location += f"#redacted-occurrence-{ordinal:04d}"
        except (OSError, ValueError):
            logical_location = None
        if skill_file.exists() or entry.is_symlink():
            if entry.is_symlink() and not is_within(resolved_entry, allowed_root):
                candidates.append(
                    _candidate(
                        scope,
                        skill_file,
                        SourceType.SKILL_BODY.value,
                        status=SourceStatus.EXCLUDED.value,
                        reason="symlink target escapes the frozen inspection root; target content was not read",
                        allowed_root=allowed_root,
                        inspection="metadata_only",
                        effective_scope={"state": "ineligible", "scope_kind": scope_kind},
                        location=logical_location,
                        provenance={"symlinked_directory": True, "target_withheld": True},
                    )
                )
                continue
            if not skill_file.exists():
                candidates.append(
                    _candidate(
                        scope,
                        skill_file,
                        SourceType.SKILL_BODY.value,
                        status=SourceStatus.MISSING.value,
                        reason="skill directory or symlink has no SKILL.md",
                        allowed_root=skill_allowed_root,
                        effective_scope={"state": "ineligible", "scope_kind": scope_kind},
                        location=logical_location,
                    )
                )
                continue
            candidates.append(
                _candidate(
                    scope,
                    skill_file,
                    SourceType.SKILL_BODY.value,
                    status=SourceStatus.DISCOVERED.value,
                    reason=f"discovered in Codex {scope_kind} skill location",
                    allowed_root=skill_allowed_root,
                    semantic_disclosure="withheld",
                    effective_scope={"state": "applicable", "scope_kind": scope_kind},
                    location=logical_location,
                    provenance={"symlinked_directory": entry.is_symlink()},
                )
            )
            for child_name, child_type in (("scripts", SourceType.SCRIPT.value),):
                child_root = entry / child_name
                if child_root.exists() and child_root.is_dir():
                    for child in sorted(child_root.rglob("*")):
                        if child.is_file():
                            candidates.append(
                                _candidate(
                                    scope,
                                    child,
                                    child_type,
                                    status=SourceStatus.EXCLUDED.value,
                                    reason="script body excluded; metadata only",
                                    allowed_root=skill_allowed_root,
                                    inspection="metadata_only",
                                    semantic_disclosure="withheld",
                                    effective_scope={"state": "referenced_only"},
                                )
                            )
    return candidates


def discover(scope: ResolvedScope, profile: dict) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    chain = _path_chain(scope.project_root, scope.selected_path)
    for directory in chain:
        candidates.extend(_discover_instruction_level(scope, directory, allowed_root=scope.workspace))
        config = directory / ".codex" / "config.toml"
        if config.exists():
            if scope.plan.project_trust == "trusted":
                status, reason, applicability = (
                    SourceStatus.DISCOVERED.value,
                    "trusted project configuration layer",
                    "applicable",
                )
            elif scope.plan.project_trust == "untrusted":
                status, reason, applicability = (
                    SourceStatus.IGNORED.value,
                    "Codex skips project configuration for an untrusted project",
                    "inapplicable",
                )
            else:
                status, reason, applicability = (
                    SourceStatus.DISCOVERED.value,
                    "project trust is unknown; effectiveness cannot be determined",
                    "unknown",
                )
            candidates.append(
                _candidate(
                    scope,
                    config,
                    SourceType.CONFIG.value,
                    status=status,
                    reason=reason,
                    allowed_root=scope.workspace,
                    effective_scope={"state": applicability, "layer": "project"},
                )
            )

    # Repository skills are discovered in each directory from CWD to root.
    for directory in reversed(chain):
        candidates.extend(
            _discover_skill_root(
                scope,
                directory / profile["rules"]["skills"]["repo_directory"],
                allowed_root=scope.workspace,
                scope_kind="repository",
            )
        )

    if scope.include_user:
        candidates.extend(
            _discover_instruction_level(scope, scope.codex_home, allowed_root=scope.codex_home, global_level=True)
        )
        user_config = scope.codex_home / "config.toml"
        if user_config.exists():
            candidates.append(
                _candidate(
                    scope,
                    user_config,
                    SourceType.CONFIG.value,
                    status=SourceStatus.DISCOVERED.value,
                    reason="Codex user configuration layer",
                    allowed_root=scope.codex_home,
                    effective_scope={"state": "applicable", "layer": "user"},
                )
            )
        user_skill_root = Path.home() / profile["rules"]["skills"]["user_directory"]
        candidates.extend(
            _discover_skill_root(
                scope,
                user_skill_root,
                allowed_root=user_skill_root,
                scope_kind="user",
            )
        )

    if scope.include_system:
        system_config = Path(profile["rules"]["configuration"]["system_filename"])
        if system_config.exists():
            candidates.append(
                _candidate(
                    scope,
                    system_config,
                    SourceType.CONFIG.value,
                    status=SourceStatus.DISCOVERED.value,
                    reason="Codex system configuration layer",
                    allowed_root=Path("/etc/codex"),
                    effective_scope={"state": "applicable", "layer": "system"},
                )
            )
        candidates.extend(
            _discover_skill_root(
                scope,
                Path(profile["rules"]["skills"]["admin_directory"]),
                allowed_root=Path("/etc/codex/skills"),
                scope_kind="admin",
            )
        )

    candidates.append(
        _candidate(
            scope,
            None,
            SourceType.OTHER.value,
            status=SourceStatus.EXCLUDED.value,
            reason="OpenAI-bundled system skills are not materialized as local files by this scanner",
            allowed_root=None,
            inspection="metadata_only",
            location="system://bundled-skills",
            effective_scope={"state": "unknown"},
        )
    )

    # Stable de-duplication keeps a source occurrence once even when discovery
    # paths converge through a symlink.
    unique: dict[tuple[str, str], SourceCandidate] = {}
    for candidate in candidates:
        unique.setdefault((candidate.source_type, candidate.location), candidate)
    return sorted(unique.values(), key=lambda item: (item.location, item.source_type))


def status_counts(candidates: Iterable[SourceCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.status] = counts.get(candidate.status, 0) + 1
    return dict(sorted(counts.items()))
