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
