from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_doctor.analysis import AnalysisRequest, analyze
from agent_doctor.canonical import canonical_json, strip_volatile
from agent_doctor.model import FixedClock
from agent_doctor.schema import validate_result


def _write_project(workspace: Path) -> None:
    (workspace / ".git").mkdir()
    (workspace / "AGENTS.md").write_text("For reports, use Markdown.\n", encoding="utf-8")
    config = workspace / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text("project_doc_max_bytes = 32768\n", encoding="utf-8")
    for name in ("copy-a", "copy-b"):
        skill = workspace / f".agents/skills/{name}/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: duplicate-review\ndescription: Review changes.\n---\nReview changes and summarize risks.\n",
            encoding="utf-8",
        )
    broken = workspace / ".agents/skills/broken/SKILL.md"
    broken.parent.mkdir(parents=True)
    broken.write_text(
        "---\nname: broken\ndescription: Review with policy.\n---\nRead `references/policy.md` before review.\n",
        encoding="utf-8",
    )


def test_vertical_pipeline_seals_one_graph_with_lineage_and_manual_actions(tmp_path: Path) -> None:
    _write_project(tmp_path)
    graph = analyze(AnalysisRequest(tmp_path, project_trust="trusted"), run_id="run-test").graph
    assert graph["sealed"] is True
    assert not validate_result(graph)
    labels = {
        assessment["label"]
        for case in graph["interaction_cases"]
        for assessment in case["assessments"]
    }
    assert {"scope_overlap", "behavioral_redundancy", "invalid_reference"}.issubset(labels)
    assert all(item["kind"] != "runtime" for item in graph["evidence"])
    assert all(item["kind"] != "inferred" for item in graph["evidence"])
    assert all(action["authority"] == "none" for action in graph["next_actions"])
    assert graph["run"]["modes"] == {
        "deterministic": "enabled",
        "semantic": "disabled",
        "repair": "proposal_only",
    }


def test_stable_result_ignores_run_clock_and_run_id(tmp_path: Path) -> None:
    _write_project(tmp_path)
    first = analyze(
        AnalysisRequest(tmp_path, project_trust="trusted"),
        clock=FixedClock(datetime(2026, 8, 17, tzinfo=timezone.utc)),
        run_id="run-one",
    ).graph
    second = analyze(
        AnalysisRequest(tmp_path, project_trust="trusted"),
        clock=FixedClock(datetime(2026, 8, 18, tzinfo=timezone.utc)),
        run_id="run-two",
    ).graph
    assert first["result_id"] == second["result_id"]
    assert strip_volatile(first) == strip_volatile(second)


def test_unknown_project_trust_abstains_without_guessing(tmp_path: Path) -> None:
    _write_project(tmp_path)
    graph = analyze(AnalysisRequest(tmp_path, project_trust="unknown")).graph
    precedence = [item for item in graph["checks"] if item["check_id"] == "deterministic.configuration.precedence"]
    assert precedence
    assert {item["state"] for item in precedence} == {"insufficient_evidence"}
    assert graph["run"]["outcome"] == "complete_with_gaps"


def test_secrets_in_config_values_and_path_names_never_enter_result(tmp_path: Path) -> None:
    sentinel = "SYNTHETIC_SECRET_DO_NOT_SEND"
    (tmp_path / ".git").mkdir()
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text(f'model_provider.api_key = "{sentinel}"\n', encoding="utf-8")
    skill = tmp_path / f".agents/skills/{sentinel}/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: safe-name\ndescription: Safe description.\n---\n", encoding="utf-8")
    graph = analyze(AnalysisRequest(tmp_path, project_trust="trusted")).graph
    assert graph["sealed"] is True
    assert sentinel not in canonical_json(graph)
    assert any("[REDACTED:" in item["location"] for item in graph["inventory"]["sources"])


def test_multiple_redacted_skill_paths_remain_distinct_inventory_records(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    secret_names = ("sk-AAAAAAAAAAAAAAAAAAAA", "sk-BBBBBBBBBBBBBBBBBBBB")
    for index, secret_name in enumerate(secret_names):
        skill = tmp_path / f".agents/skills/{secret_name}/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            f"---\nname: safe-{index}\ndescription: Safe description {index}.\n---\n",
            encoding="utf-8",
        )
    graph = analyze(AnalysisRequest(tmp_path, project_trust="trusted")).graph
    skill_sources = [item for item in graph["inventory"]["sources"] if item["type"] == "skill_body"]
    assert len(skill_sources) == 2
    assert len({item["source_id"] for item in skill_sources}) == 2
    serialized = canonical_json(graph)
    assert all(secret_name not in serialized for secret_name in secret_names)
