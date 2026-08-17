from __future__ import annotations

import json
from pathlib import Path

from agent_doctor.cli import main


def test_scan_json_and_ci_exit_contract(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_text("Use Markdown.\n", encoding="utf-8")
    assert main(["scan", str(tmp_path), "--format", "json"]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert graph["sealed"] is True

    assert main(["scan", str(tmp_path), "--format", "ci"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["decision"]["outcome"] == "satisfied"
    assert envelope["decision"]["result_ref"] == envelope["result"]["result_id"]


def test_scan_default_is_human_readable_and_debug_is_explicit(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_text("Use Markdown.\n", encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 0
    terminal = capsys.readouterr().out
    assert "What needs attention" in terminal
    assert "Skill health" in terminal

    assert main(["scan", str(tmp_path), "--format", "debug"]) == 0
    debug = capsys.readouterr().out
    assert "cases:" in debug
    assert "Technical reference" not in debug


def test_scan_semantic_coverage_defaults_on_and_can_be_disabled(tmp_path: Path, capsys) -> None:
    (tmp_path / "AGENTS.md").write_text("Use Markdown.\n", encoding="utf-8")
    assert main(["scan", str(tmp_path), "--format", "json"]) == 0
    default_graph = json.loads(capsys.readouterr().out)
    assert default_graph["run"]["modes"]["semantic"] == "enabled"
    assert any(
        item["reason"].get("code") == "semantic_provider_run_pending"
        for item in default_graph["checks"]
    )

    assert main(
        [
            "scan",
            str(tmp_path),
            "--semantic-mode",
            "disabled",
            "--format",
            "json",
        ]
    ) == 0
    disabled_graph = json.loads(capsys.readouterr().out)
    assert disabled_graph["run"]["modes"]["semantic"] == "disabled"
    assert any(
        item["reason"].get("code") == "semantic_mode_disabled"
        for item in disabled_graph["checks"]
    )


def test_semantic_run_with_one_selected_skill_is_not_applicable_without_provider(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    skill = tmp_path / ".agents/skills/only/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: only
description: Review one bounded local task.
---
# Only
Review the selected local task and report evidence.
""",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifacts"

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("a one-Skill scope must not start a provider")

    monkeypatch.setattr(
        "agent_doctor.cli.invoke_codex_provider", forbidden_provider
    )
    assert main(
        [
            "semantic",
            "run",
            str(tmp_path),
            "--artifact-dir",
            str(artifact_dir),
        ]
    ) == 0
    terminal = capsys.readouterr().out
    assert "fewer than two Skills were selected" in terminal
    assert "no provider call started" in terminal
    assert f"Artifacts: {artifact_dir}" in terminal

    status = json.loads(
        (artifact_dir / "semantic-status.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (artifact_dir / "result.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "not_applicable"
    assert status["provider_started"] is False
    assert status["result_ref"] == result["result_id"]
    assert result["sealed"] is True
    assert any(
        item["reason"].get("code")
        == "semantic_relationship_scope_not_applicable"
        for item in result["checks"]
    )


def test_semantic_run_help_describes_repeatable_exact_scope(capsys) -> None:
    try:
        main(["semantic", "run", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    help_text = capsys.readouterr().out
    assert "exact selected Skill source ID or displayed location" in help_text
    assert "when omitted, use the bounded discovered" in help_text
    assert "exact Skill source ID or displayed location to" in help_text
    assert "from the semantic scope (repeatable)" in help_text


def test_spec_cli_compact_summary(capsys) -> None:
    code = main(
        [
            "spec",
            "run",
            "test-spec/fixtures/golden-v0.1.json",
            "--id",
            "G-001",
            "--summary",
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["counts"]["passed"] == 1
    assert report["measurement_status"] == "not_performed"


def test_propose_cli_is_non_executable(tmp_path: Path, capsys) -> None:
    from agent_doctor.golden import execute

    suite = json.loads(Path("test-spec/fixtures/golden-v0.1.json").read_text(encoding="utf-8"))
    case = next(item for item in suite["cases"] if item["id"] == "G-004")
    graph = execute(case)["graph"]
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(graph), encoding="utf-8")
    case_ref = graph["interaction_cases"][0]["case_id"]
    assert main(["propose", str(result_path), "--case", case_ref]) == 0
    proposal = json.loads(capsys.readouterr().out)
    assert proposal["authority"] == "none"
    assert proposal["executable_operations"] == []


def test_model_resolve_cli_is_local_configurable_and_explicit_about_readiness(capsys) -> None:
    code = main(
        [
            "model",
            "resolve",
            "--capability",
            "semantic.reasoning_quality_first",
            "--available-model",
            "gpt-5.6-sol",
            "--require-qualified",
            "--as-of",
            "2026-08-17",
        ]
    )
    assert code == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["selected_model"] == "gpt-5.6-sol"
    assert decision["reasoning_effort"] == "max"
    assert decision["invocation_ready"] is False
    assert decision["blockers"] == ["model_not_qualified_for_product_semantics"]

    strict_code = main(
        [
            "model",
            "resolve",
            "--capability",
            "semantic.reasoning_quality_first",
            "--available-model",
            "gpt-5.6-sol",
            "--require-qualified",
            "--require-ready",
            "--as-of",
            "2026-08-17",
        ]
    )
    assert strict_code == 3
    capsys.readouterr()


def test_model_routing_spec_cli(capsys) -> None:
    assert main(["model", "spec", "--summary"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["counts"] == {"failed": 0, "invalid": 0, "passed": 11}
    assert report["measurement_status"] == "not_performed"
