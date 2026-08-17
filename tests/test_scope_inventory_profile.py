from __future__ import annotations

import copy
import json
from pathlib import Path

from agent_doctor.analysis import AnalysisRequest, analyze
from agent_doctor.inventory import discover
from agent_doctor.profile import compatibility_decision, load_profile, validate_profile
from agent_doctor.scope import ScopeOptions, plan_scope


def test_reviewed_bundled_profile_is_codex_attributable() -> None:
    profile = load_profile()
    assert not validate_profile(profile)
    assert profile["ecosystem"] == "codex"
    assert compatibility_decision(profile).usable
    assert all(
        item["uri"].startswith(("https://learn.chatgpt.com/", "https://developers.openai.com/"))
        for item in profile["provenance"]
    )


def test_unknown_stale_and_incompatible_profiles_cannot_prove_rules() -> None:
    profile = load_profile()
    for status, expected in (("unknown", "insufficient_evidence"), ("stale", "insufficient_evidence"), ("incompatible", "error")):
        changed = copy.deepcopy(profile)
        changed["status"] = status
        decision = compatibility_decision(changed)
        assert not decision.usable
        assert decision.state == expected


def test_scope_is_frozen_relative_and_manual_only(tmp_path: Path) -> None:
    profile = load_profile()
    selected = tmp_path / "api"
    selected.mkdir()
    scope = plan_scope(ScopeOptions(tmp_path, selected_path=selected), profile)
    assert scope.plan.workspace_identity == "workspace://"
    assert scope.plan.selected_regions == ("workspace://api",)
    assert scope.plan.modification_boundary == {"mode": "proposal_only", "targets": []}
    assert scope.plan.semantic_disclosure_boundary["mode"] == "disabled"


def test_empty_instruction_is_ignored_without_inventing_a_shadowing_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codex_home.mkdir(parents=True)
    (codex_home / "AGENTS.md").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    profile = load_profile()
    scope = plan_scope(ScopeOptions(workspace, include_user=True), profile)
    candidate = next(
        item
        for item in discover(scope, profile)
        if item.location == "user://.codex/AGENTS.md"
    )

    assert candidate.status == "ignored"
    assert candidate.effective_scope == {
        "state": "inapplicable",
        "directory": "user://.codex",
    }
    assert "empty instruction file" in candidate.status_reason


def test_outside_skill_symlink_is_inventoried_but_not_inspected(tmp_path: Path) -> None:
    profile = load_profile()
    skill_root = tmp_path / ".agents/skills"
    skill_root.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-skill"
    outside.mkdir()
    (outside / "SKILL.md").write_text("---\nname: outside\ndescription: outside\n---\n", encoding="utf-8")
    (skill_root / "outside").symlink_to(outside, target_is_directory=True)
    scope = plan_scope(ScopeOptions(tmp_path), profile)
    candidates = discover(scope, profile)
    candidate = next(item for item in candidates if item.source_type == "skill_body")
    assert candidate.status == "excluded"
    assert candidate.inspection == "metadata_only"
    assert candidate.location == "workspace://.agents/skills/outside/SKILL.md"
    assert candidate.provenance == {"symlinked_directory": True, "target_withheld": True}


def test_outside_skill_root_symlink_is_rejected_before_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside-skills"
    outside_skill = outside / "hidden"
    outside_skill.mkdir(parents=True)
    (outside_skill / "SKILL.md").write_text(
        "---\nname: hidden\ndescription: Must stay outside scope.\n---\n",
        encoding="utf-8",
    )
    skill_parent = workspace / ".agents"
    skill_parent.mkdir(parents=True)
    (skill_parent / "skills").symlink_to(outside, target_is_directory=True)

    profile = load_profile()
    scope = plan_scope(ScopeOptions(workspace), profile)
    candidates = discover(scope, profile)
    root_record = next(item for item in candidates if item.location == "workspace://.agents/skills")

    assert root_record.status == "excluded"
    assert root_record.inspection == "metadata_only"
    assert root_record.provenance == {"symlinked_root": True, "target_withheld": True}
    assert all(item.location != "workspace://.agents/skills/hidden/SKILL.md" for item in candidates)


def _write_skill(path: Path, *, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: Test {name}.\n---\nPerform the test task.\n",
        encoding="utf-8",
    )


def test_include_user_inventories_codex_home_and_nested_system_skills_as_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_skill(codex_home / "skills/personal/SKILL.md", name="personal")
    _write_skill(codex_home / "skills/.system/bundled/SKILL.md", name="bundled")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    profile = load_profile()
    scope = plan_scope(ScopeOptions(workspace, include_user=True), profile)
    candidates = discover(scope, profile)
    observed = [
        item
        for item in candidates
        if item.source_type == "skill_body"
        and (item.provenance or {}).get("inventory_basis") == "local_filesystem_observation"
    ]

    assert len(observed) == 2
    assert {item.effective_scope["state"] for item in observed} == {"unknown"}
    assert {item.effective_scope["runtime_selection_observed"] for item in observed} == {False}
    assert all(item.provenance["runtime_selection"] == "unobserved" for item in observed)
    assert "user://.codex/skills" in scope.plan.discovery_boundary["roots"]
    assert "user://.codex/plugins/cache" in scope.plan.discovery_boundary["roots"]


def test_plugin_cache_versions_are_inventoried_without_runtime_duplicate_finding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for version in ("1.0.0", "2.0.0"):
        plugin_root = codex_home / f"plugins/cache/local/demo/{version}"
        manifest = plugin_root / ".codex-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"name": "demo", "version": version, "skills": "./skills"}),
            encoding="utf-8",
        )
        _write_skill(plugin_root / "skills/group/shared/SKILL.md", name="shared-cache-skill")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    graph = analyze(AnalysisRequest(workspace, include_user=True)).graph
    cached = [
        item
        for item in graph["inventory"]["sources"]
        if item["type"] == "skill_body"
        and item["provenance"].get("plugin_name") == "demo"
    ]

    assert len(cached) == 2
    assert {item["effective_scope"]["state"] for item in cached} == {"unknown"}
    assert graph["run"]["outcome"] == "complete_with_gaps"
    assert any(
        item["check_id"] == "deterministic.skill.local-observed-applicability"
        and item["state"] == "insufficient_evidence"
        for item in graph["checks"]
    )
    assert all(item["check_id"] != "deterministic.skill.duplicate-installation" for item in graph["checks"])


def test_invalid_plugin_manifest_makes_inventory_partial_not_complete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest = codex_home / "plugins/cache/local/broken/1.0/.codex-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    graph = analyze(AnalysisRequest(workspace, include_user=True)).graph
    inventory_checks = [item for item in graph["checks"] if item["check_id"] == "deterministic.inventory.complete"]

    assert graph["sealed"] is True
    assert graph["run"]["outcome"] == "complete_with_gaps"
    assert len(inventory_checks) == 1
    assert inventory_checks[0]["state"] == "error"
    assert inventory_checks[0]["reason"]["code"] == "inventory_coverage_gap"
