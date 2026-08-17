from __future__ import annotations

import copy
from pathlib import Path

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
