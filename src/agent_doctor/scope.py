"""Frozen analysis-scope planning and path identities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import ScopePlan
from .privacy import effective_codex_home, is_within, redact_secrets


class ScopeError(ValueError):
    pass


@dataclass(frozen=True)
class ScopeOptions:
    workspace: Path
    selected_path: Path | None = None
    include_user: bool = False
    include_system: bool = False
    project_trust: str = "unknown"
    semantic_mode: str = "disabled"


@dataclass(frozen=True)
class ResolvedScope:
    plan: ScopePlan
    workspace: Path
    selected_path: Path
    project_root: Path
    codex_home: Path
    inspection_roots: tuple[Path, ...]
    include_user: bool
    include_system: bool

    def display_location(self, path: Path) -> str:
        resolved = path.resolve(strict=False)
        if is_within(resolved, self.workspace):
            relative = resolved.relative_to(self.workspace.resolve(strict=False)).as_posix()
            display = "workspace://" + (relative if relative != "." else "")
            return redact_secrets(display).text
        user_root = Path.home().resolve(strict=False)
        if is_within(resolved, user_root):
            relative = resolved.relative_to(user_root).as_posix()
            return redact_secrets(f"user://{relative}").text
        return redact_secrets(f"system://{resolved.as_posix().lstrip('/')}").text


def _find_project_root(selected: Path, workspace: Path) -> Path:
    current = selected
    candidates: list[Path] = []
    while is_within(current, workspace):
        if (current / ".git").exists():
            candidates.append(current)
        if current == workspace:
            break
        current = current.parent
    return candidates[-1] if candidates else workspace


def plan_scope(options: ScopeOptions, profile: dict) -> ResolvedScope:
    workspace = options.workspace.expanduser().resolve(strict=True)
    if not workspace.is_dir():
        raise ScopeError("workspace must be a directory")
    selected = (options.selected_path or workspace).expanduser().resolve(strict=True)
    if not selected.is_dir():
        selected = selected.parent
    if not is_within(selected, workspace):
        raise ScopeError("selected path must stay inside the workspace")
    if options.project_trust not in {"trusted", "untrusted", "unknown"}:
        raise ScopeError("project trust must be trusted, untrusted, or unknown")
    if options.semantic_mode != "disabled":
        raise ScopeError(
            "the Stage 05 product slice keeps semantic analysis disabled; "
            "scripted semantic behavior exists only inside the synthetic test runner"
        )

    project_root = _find_project_root(selected, workspace)
    codex_home = effective_codex_home().resolve(strict=False)
    discovery_roots = ["workspace://"]
    inspection_roots = [workspace]
    if options.include_user:
        discovery_roots.extend(
            [
                "user://.codex",
                "user://.agents/skills",
                "user://.codex/skills",
                "user://.codex/plugins/cache",
            ]
        )
        inspection_roots.extend([codex_home, Path.home() / ".agents" / "skills"])
    if options.include_system:
        discovery_roots.extend(["system://etc/codex/config.toml", "system://etc/codex/skills"])
        inspection_roots.extend([Path("/etc/codex")])

    selected_relative = selected.relative_to(workspace).as_posix()
    profile_ref = f"{profile['profile_id']}@{profile['profile_version']}"
    exclusions = [
        {"subject": "script bodies", "reason": "metadata-only in deterministic mode"},
        {"subject": "paths outside inspection roots", "reason": "scope cannot expand through references"},
        {"subject": "runtime traces", "reason": "no MVP runtime evidence producer"},
        {"subject": "repair writes", "reason": "Stage 05 slice is proposal/manual-only"},
    ]
    if not options.include_user:
        exclusions.append({"subject": "user configuration", "reason": "not selected; use --include-user"})
    if not options.include_system:
        exclusions.append({"subject": "admin/system files", "reason": "not selected; use --include-system"})
    semantic_boundary = {
        "mode": options.semantic_mode,
        "eligible": [] if options.semantic_mode == "disabled" else ["fixture-declared minimized excerpts"],
        "external_network": False,
    }
    plan = ScopePlan.create(
        workspace_identity="workspace://",
        selected_regions=["workspace://" + (selected_relative if selected_relative != "." else "")],
        discovery_boundary={"roots": discovery_roots, "source_types": ["skills", "instructions", "config"]},
        inspection_boundary={"roots": discovery_roots, "scripts": "metadata_only"},
        semantic_disclosure_boundary=semantic_boundary,
        modification_boundary={"mode": "proposal_only", "targets": []},
        exclusions=exclusions,
        project_trust=options.project_trust,
        platform_profile=profile_ref,
    )
    return ResolvedScope(
        plan=plan,
        workspace=workspace,
        selected_path=selected,
        project_root=project_root,
        codex_home=codex_home,
        inspection_roots=tuple(path.resolve(strict=False) for path in inspection_roots),
        include_user=options.include_user,
        include_system=options.include_system,
    )
