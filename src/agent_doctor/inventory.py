"""Codex-profile-driven discovery and complete source inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .canonical import stable_id
from .model import SourceRecord
from .privacy import SafeReader, is_within, redact_secrets
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
    revision: str | None = None,
    readability: str = "unknown",
    sensitivity: tuple[str, ...] = (),
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
        revision=revision,
        readability=readability,
        sensitivity=sensitivity,
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
    effective_state: str = "applicable",
    provenance: dict | None = None,
    max_depth: int = 1,
    max_skills: int = 512,
    max_entries: int = 4_096,
) -> list[SourceCandidate]:
    if not root.exists() or not root.is_dir():
        return []
    if not is_within(root, allowed_root):
        try:
            relative = root.absolute().relative_to(scope.workspace.absolute()).as_posix()
            logical_root = "workspace://" + relative
        except ValueError:
            logical_root = scope.display_location(root)
        return [
            _candidate(
                scope,
                root,
                SourceType.OTHER.value,
                status=SourceStatus.EXCLUDED.value,
                reason="Skill discovery root escapes the frozen inspection boundary",
                allowed_root=allowed_root,
                inspection="metadata_only",
                effective_scope={"state": "ineligible", "scope_kind": scope_kind},
                location=logical_root,
                provenance={**(provenance or {}), "symlinked_root": True, "target_withheld": True},
            )
        ]
    candidates: list[SourceCandidate] = []
    ordinal = 0
    skill_count = 0
    stopped = False
    excluded_subtrees = {"scripts", "references", "assets", "agents", "node_modules", ".git", ".codex-plugin"}

    def merged_provenance(**values: object) -> dict:
        return {**(provenance or {}), **values}

    def coverage_record(directory: Path, *, status: str, reason: str) -> None:
        candidates.append(
            _candidate(
                scope,
                directory,
                SourceType.OTHER.value,
                status=status,
                reason=reason,
                allowed_root=allowed_root,
                inspection="metadata_only",
                effective_scope={"state": "unknown", "scope_kind": scope_kind},
                provenance=merged_provenance(coverage_gap=True),
            )
        )

    def walk(directory: Path, depth: int) -> None:
        nonlocal ordinal, skill_count, stopped
        if stopped:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except (OSError, PermissionError):
            coverage_record(directory, status=SourceStatus.UNREADABLE.value, reason="skill discovery directory is unreadable")
            return
        for entry in entries:
            if stopped:
                return
            ordinal += 1
            if ordinal > max_entries:
                coverage_record(
                    root,
                    status=SourceStatus.TRUNCATED.value,
                    reason=f"skill discovery stopped at the declared {max_entries}-entry traversal bound",
                )
                stopped = True
                return
            skill_file = entry / "SKILL.md"
            resolved_entry = entry.resolve(strict=False)
            skill_allowed_root = resolved_entry
            relative_entry = entry.relative_to(root).as_posix()
            try:
                raw_logical_location = scope.display_location(root) + "/" + relative_entry + "/SKILL.md"
                location_redaction = redact_secrets(raw_logical_location)
                logical_location = location_redaction.text
                if location_redaction.changed:
                    logical_location += f"#redacted-occurrence-{ordinal:04d}"
            except (OSError, ValueError):
                logical_location = None
            has_skill = skill_file.exists() or entry.is_symlink()
            if has_skill:
                skill_count += 1
                if skill_count > max_skills:
                    coverage_record(
                        root,
                        status=SourceStatus.TRUNCATED.value,
                        reason=f"skill discovery stopped at the declared {max_skills}-Skill inventory bound",
                    )
                    stopped = True
                    return
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
                            provenance=merged_provenance(symlinked_directory=True, target_withheld=True),
                        )
                    )
                elif not skill_file.exists():
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
                            provenance=merged_provenance(symlinked_directory=entry.is_symlink()),
                        )
                    )
                else:
                    candidates.append(
                        _candidate(
                            scope,
                            skill_file,
                            SourceType.SKILL_BODY.value,
                            status=SourceStatus.DISCOVERED.value,
                            reason=f"discovered in Codex {scope_kind} skill location",
                            allowed_root=skill_allowed_root,
                            semantic_disclosure="withheld",
                            effective_scope={
                                "state": effective_state,
                                "scope_kind": scope_kind,
                                "runtime_selection_observed": False,
                            },
                            location=logical_location,
                            provenance=merged_provenance(symlinked_directory=entry.is_symlink()),
                        )
                    )
                    child_root = entry / "scripts"
                    if child_root.exists() and child_root.is_dir():
                        script_count = 0
                        try:
                            script_children = sorted(child_root.rglob("*"))
                        except (OSError, PermissionError):
                            coverage_record(
                                child_root,
                                status=SourceStatus.UNREADABLE.value,
                                reason="script metadata directory is unreadable",
                            )
                            script_children = []
                        for child in script_children:
                            try:
                                is_file = child.is_file()
                            except OSError:
                                coverage_record(
                                    child,
                                    status=SourceStatus.UNREADABLE.value,
                                    reason="script metadata entry is unreadable",
                                )
                                continue
                            if not is_file:
                                continue
                            script_count += 1
                            if script_count > 256:
                                coverage_record(
                                    child_root,
                                    status=SourceStatus.TRUNCATED.value,
                                    reason="script metadata inventory stopped at the declared 256-file per-Skill bound",
                                )
                                break
                            candidates.append(
                                _candidate(
                                    scope,
                                    child,
                                    SourceType.SCRIPT.value,
                                    status=SourceStatus.EXCLUDED.value,
                                    reason="script body excluded; metadata only",
                                    allowed_root=skill_allowed_root,
                                    inspection="metadata_only",
                                    semantic_disclosure="withheld",
                                    effective_scope={"state": "referenced_only", "parent_applicability": effective_state},
                                    provenance=merged_provenance(parent_skill=logical_location),
                                )
                            )
            if (
                depth < max_depth
                and not entry.is_symlink()
                and entry.name not in excluded_subtrees
                and entry.is_dir()
            ):
                walk(entry, depth + 1)

    walk(root, 1)
    return candidates


def _discover_plugin_cache(scope: ResolvedScope, cache_root: Path) -> list[SourceCandidate]:
    """Inventory manifest-declared cached Skills without claiming activation."""

    if not cache_root.exists() or not cache_root.is_dir():
        return []
    candidates: list[SourceCandidate] = []
    reader = SafeReader(max_bytes=262_144)
    manifest_count = 0

    def plugin_gap(path: Path, *, status: str, reason: str, allowed_root: Path = cache_root) -> SourceCandidate:
        return _candidate(
            scope,
            path,
            SourceType.OTHER.value,
            status=status,
            reason=reason,
            allowed_root=allowed_root,
            inspection="metadata_only",
            effective_scope={"state": "unknown", "scope_kind": "local_plugin_cache"},
            provenance={"inventory_basis": "local_filesystem_observation", "coverage_gap": True},
        )

    try:
        marketplaces = sorted((item for item in cache_root.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
    except (OSError, PermissionError):
        return [plugin_gap(cache_root, status=SourceStatus.UNREADABLE.value, reason="local plugin cache root is unreadable")]

    for marketplace in marketplaces:
        try:
            plugins = sorted((item for item in marketplace.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
        except (OSError, PermissionError):
            candidates.append(
                plugin_gap(
                    marketplace,
                    status=SourceStatus.UNREADABLE.value,
                    reason="plugin cache namespace is unreadable",
                )
            )
            continue
        for plugin in plugins:
            try:
                versions = sorted((item for item in plugin.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
            except (OSError, PermissionError):
                candidates.append(
                    plugin_gap(
                        plugin,
                        status=SourceStatus.UNREADABLE.value,
                        reason="plugin cache package directory is unreadable",
                    )
                )
                continue
            for version_root in versions:
                manifest = version_root / ".codex-plugin" / "plugin.json"
                if not manifest.is_file():
                    continue
                manifest_count += 1
                if manifest_count > 256:
                    candidates.append(
                        plugin_gap(
                            cache_root,
                            status=SourceStatus.TRUNCATED.value,
                            reason="plugin cache discovery stopped at the declared 256-manifest bound",
                        )
                    )
                    return candidates
                if not is_within(version_root, cache_root):
                    candidates.append(
                        _candidate(
                            scope,
                            manifest,
                            SourceType.OTHER.value,
                            status=SourceStatus.EXCLUDED.value,
                            reason="plugin cache entry escapes the frozen inspection root",
                            allowed_root=cache_root,
                            inspection="metadata_only",
                            effective_scope={"state": "ineligible", "scope_kind": "local_plugin_cache"},
                            provenance={"inventory_basis": "local_filesystem_observation", "coverage_gap": True},
                        )
                    )
                    continue
                result = reader.read_text(
                    manifest,
                    allowed_root=version_root,
                    purpose="plugin_skill_inventory",
                    source_type=SourceType.OTHER.value,
                )
                manifest_provenance = {
                    "inventory_basis": "local_filesystem_observation",
                    "manifest_location": scope.display_location(manifest),
                    "manifest_revision": result.revision,
                    "runtime_selection": "unobserved",
                    "installation_marker_present": (plugin / ".codex-remote-plugin-install.json").is_file(),
                }
                if result.status != "read" or result.content is None:
                    candidates.append(
                        _candidate(
                            scope,
                            manifest,
                            SourceType.OTHER.value,
                            status=SourceStatus.UNREADABLE.value,
                            reason=result.diagnostic or "plugin manifest could not be read",
                            allowed_root=version_root,
                            inspection="metadata_only",
                            effective_scope={"state": "unknown", "scope_kind": "local_plugin_cache"},
                            provenance={**manifest_provenance, "coverage_gap": True},
                        )
                    )
                    continue
                try:
                    metadata = json.loads(result.content)
                except json.JSONDecodeError:
                    candidates.append(
                        _candidate(
                            scope,
                            manifest,
                            SourceType.OTHER.value,
                            status=SourceStatus.UNREADABLE.value,
                            reason="plugin manifest is not valid JSON",
                            allowed_root=version_root,
                            inspection="metadata_only",
                            effective_scope={"state": "unknown", "scope_kind": "local_plugin_cache"},
                            provenance={**manifest_provenance, "coverage_gap": True},
                        )
                    )
                    continue
                if not isinstance(metadata, dict):
                    candidates.append(
                        plugin_gap(
                            manifest,
                            status=SourceStatus.UNREADABLE.value,
                            reason="plugin manifest root must be a JSON object",
                            allowed_root=version_root,
                        )
                    )
                    continue
                declared_name = redact_secrets(str(metadata.get("name", plugin.name))).text
                declared_version = redact_secrets(str(metadata.get("version", version_root.name))).text
                skills_value = metadata.get("skills")
                if skills_value is None:
                    continue
                if not isinstance(skills_value, str) or not skills_value.strip():
                    candidates.append(
                        plugin_gap(
                            manifest,
                            status=SourceStatus.UNREADABLE.value,
                            reason="plugin manifest Skill root must be a non-empty relative string",
                            allowed_root=version_root,
                        )
                    )
                    continue
                skills_root = (version_root / skills_value).resolve(strict=False)
                plugin_provenance = {
                    **manifest_provenance,
                    "plugin_name": declared_name,
                    "plugin_version": declared_version,
                    "cache_namespace": redact_secrets(marketplace.name).text,
                }
                if not is_within(skills_root, version_root):
                    candidates.append(
                        _candidate(
                            scope,
                            manifest,
                            SourceType.OTHER.value,
                            status=SourceStatus.EXCLUDED.value,
                            reason="plugin manifest declares a Skill root outside its cache entry",
                            allowed_root=version_root,
                            inspection="metadata_only",
                            effective_scope={"state": "ineligible", "scope_kind": "local_plugin_cache"},
                            provenance={**plugin_provenance, "coverage_gap": True},
                        )
                    )
                    continue
                if not skills_root.is_dir():
                    candidates.append(
                        _candidate(
                            scope,
                            skills_root,
                            SourceType.OTHER.value,
                            status=SourceStatus.MISSING.value,
                            reason="plugin manifest declares a missing Skill root",
                            allowed_root=version_root,
                            inspection="metadata_only",
                            effective_scope={"state": "unknown", "scope_kind": "local_plugin_cache"},
                            provenance={**plugin_provenance, "coverage_gap": True},
                        )
                    )
                    continue
                candidates.extend(
                    _discover_skill_root(
                        scope,
                        skills_root,
                        allowed_root=version_root,
                        scope_kind="locally observed plugin cache",
                        effective_state="unknown",
                        provenance=plugin_provenance,
                        max_depth=3,
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
        local_skill_root = scope.codex_home / "skills"
        candidates.extend(
            _discover_skill_root(
                scope,
                local_skill_root,
                allowed_root=local_skill_root,
                scope_kind="locally observed Codex-home",
                effective_state="unknown",
                provenance={
                    "inventory_basis": "local_filesystem_observation",
                    "documentation_status": "not_a_documented_discovery_root_in_selected_profile",
                    "runtime_selection": "unobserved",
                },
                max_depth=2,
            )
        )
        candidates.extend(_discover_plugin_cache(scope, scope.codex_home / "plugins" / "cache"))

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
            reason=(
                "the reviewed profile does not expose a complete enumerable system-Skill source; "
                "locally observed copies do not prove the runtime bundle"
            ),
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
