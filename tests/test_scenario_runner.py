from __future__ import annotations

from pathlib import Path

from agent_doctor.scenario import SuitePaths, report_exit_code, run_suite, validate_suite_file


ROOT = Path("test-spec")
SCHEMA = ROOT / "schema/scenario-suite.schema.json"
GOLDEN = ROOT / "fixtures/golden-v0.1.json"
CATALOG = ROOT / "scenarios/stage-04-catalog-v0.1.json"


def test_stage_04_suites_validate() -> None:
    assert validate_suite_file(SuitePaths(GOLDEN, SCHEMA))["valid"]
    assert validate_suite_file(SuitePaths(CATALOG, SCHEMA))["valid"]


def test_all_reviewed_goldens_execute_exactly_three_times() -> None:
    report = run_suite(SuitePaths(GOLDEN, SCHEMA, GOLDEN), repetitions=3)
    assert report["counts"] == {"passed": 20, "failed": 0, "unsupported": 0, "invalid": 0}
    assert report["evidence_outcome"] == "valid"
    assert report["gate_outcome"] == "satisfied_for_executed_scenarios"
    assert report["measurement_status"] == "not_performed"
    assert report_exit_code(report) == 0


def test_catalog_executes_deterministic_and_semantic_slices_and_reports_repair_scope() -> None:
    report = run_suite(SuitePaths(CATALOG, SCHEMA, GOLDEN))
    assert report["counts"] == {"passed": 101, "failed": 0, "unsupported": 31, "invalid": 0}
    assert report_exit_code(report) == 0
    unsupported = {item["id"] for item in report["cases"] if item["status"] == "unsupported"}
    passed = {item["id"] for item in report["cases"] if item["status"] == "passed"}
    assert "S-SEM-001" in passed
    assert "S-SEM-018" in passed
    assert "S-REP-030" in unsupported
    assert "S-CMP-008" in unsupported

    strict = run_suite(SuitePaths(CATALOG, SCHEMA, GOLDEN), require_all=True)
    assert strict["evidence_outcome"] == "execution_failed"
    assert strict["gate_outcome"] == "not_evaluated"
    assert report_exit_code(strict) == 3


def test_missing_selected_case_is_runner_execution_failure() -> None:
    report = run_suite(SuitePaths(GOLDEN, SCHEMA, GOLDEN), selected_ids={"G-999"})
    assert report["counts"]["invalid"] == 1
    assert report["evidence_outcome"] == "execution_failed"
    assert report_exit_code(report) == 3
