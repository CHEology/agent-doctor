"""Stage 04 suite validation, execution, and gate-result reporting."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import catalog, golden
from .canonical import canonical_json, strip_volatile
from .jsonschema_subset import SchemaError, validate
from .types import SUBSTANTIVE_LABELS
from .version import SCENARIO_SCHEMA_VERSION, __version__


@dataclass(frozen=True)
class SuitePaths:
    suite: Path
    schema: Path
    golden: Path | None = None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_suite(suite: Any, schema: dict[str, Any]) -> list[SchemaError]:
    errors = validate(suite, schema)
    if not isinstance(suite, dict) or not isinstance(suite.get("cases"), list):
        return errors
    identifiers = [item.get("id") for item in suite["cases"] if isinstance(item, dict)]
    if len(identifiers) != len(set(identifiers)):
        errors.append(SchemaError("$.cases", "scenario identifiers must be unique"))
    for index, case in enumerate(suite["cases"]):
        if not isinstance(case, dict):
            continue
        if case.get("schema_version") != suite.get("schema_version"):
            errors.append(SchemaError(f"$.cases[{index}].schema_version", "must match suite schema version"))
        labels = case.get("expected", {}).get("diagnostic", {}).get("substantive_labels", [])
        for label in labels:
            if label not in SUBSTANTIVE_LABELS:
                errors.append(SchemaError(f"$.cases[{index}].expected.diagnostic.substantive_labels", f"unknown product label: {label}"))
        state = case.get("expected", {}).get("diagnostic", {}).get("check_state")
        if state == "not_applicable" and case.get("expected", {}).get("diagnostic", {}).get("check_id") != "not_applicable":
            errors.append(SchemaError(f"$.cases[{index}].expected.diagnostic", "test-only not_applicable must remain wholly outside product diagnostics"))
    return sorted(errors, key=lambda item: (item.path, item.message))


def validate_suite_file(paths: SuitePaths) -> dict[str, Any]:
    try:
        suite = load_json(paths.suite)
        schema = load_json(paths.schema)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "agent-doctor-test-validation/0.1",
            "valid": False,
            "suite": str(paths.suite),
            "errors": [{"path": "$", "message": f"{type(exc).__name__}: {exc}"}],
        }
    errors = validate_suite(suite, schema)
    return {
        "schema_version": "agent-doctor-test-validation/0.1",
        "valid": not errors,
        "suite": str(paths.suite),
        "suite_id": suite.get("suite_id") if isinstance(suite, dict) else None,
        "case_count": len(suite.get("cases", [])) if isinstance(suite, dict) else 0,
        "errors": [{"path": item.path, "message": item.message} for item in errors],
    }


def _prohibited_assertions(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, bool]:
    diagnostic = actual["diagnostic"]
    labels = diagnostic["substantive_labels"]
    state = diagnostic["check_state"]
    assertions: dict[str, bool] = {}
    graph = actual.get("graph")
    for index, prohibited in enumerate(case["prohibited_outcomes"]):
        lowered = prohibited.casefold()
        passed = True
        for label in SUBSTANTIVE_LABELS:
            if label not in lowered:
                continue
            if lowered.startswith("only "):
                passed = labels != [label]
            elif "same claim/region/dimension" in lowered or "same dimension" in lowered:
                if graph:
                    dimensions = {
                        item["label"]: item["dimension_ref"]
                        for item in graph["interaction_cases"][0].get("assessments", [])
                    }
                    passed = dimensions.get("semantic_conflict") != dimensions.get("behavioral_redundancy")
            elif lowered.startswith(label) or lowered.startswith("active " + label) or lowered.startswith("generic " + label):
                passed = label not in labels
            elif any(marker in lowered for marker in (" based ", " from ", " because ")):
                passed = label not in labels
        if re.search(r"\bpass\b", lowered) and not lowered.startswith("suppression"):
            passed = passed and state != "pass"
        if "not_run" in lowered:
            passed = passed and state != "not_run"
        if "insufficient_evidence" in lowered:
            passed = passed and state != "insufficient_evidence"
        if "two user-visible duplicate alerts" in lowered and graph:
            passed = passed and len(graph.get("finding_groups", [])) == 1
        if "reading outside target" in lowered or "reading or sending withheld bodies" in lowered:
            passed = passed and all(
                item not in actual["inventory"].get("inspected_locations", [])
                for item in case["expected"]["inventory"].get("must_exclude", [])
            )
        assertions[f"prohibited[{index}]"] = passed
    return assertions


def _compare_expected(case: dict[str, Any], actual: dict[str, Any], *, golden_suite: bool) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    expected = case["expected"]
    assertions: dict[str, bool] = {
        "diagnostic_exact": actual["diagnostic"] == expected["diagnostic"],
        "evidence_kinds_exact": actual["evidence_kinds"] == expected["evidence_kinds"],
        "coverage_exact": actual["coverage"] == expected["coverage"],
        "operation_exact": actual["operation"] == expected["operation"],
        "inventory_complete": actual["inventory"]["complete"] is expected["inventory"]["complete"],
        "inventory_must_include": all(
            item in actual["inventory"]["locations"]
            for item in expected["inventory"]["must_include"]
        ),
        "inspection_must_exclude": all(
            item not in actual["inventory"].get("inspected_locations", [])
            for item in expected["inventory"]["must_exclude"]
        ),
    }
    expected_counts = expected["inventory"]["expected_status_counts"]
    if golden_suite:
        assertions["inventory_status_counts"] = actual["inventory"]["status_counts"] == expected_counts
    else:
        assertions["inventory_status_counts"] = all(
            actual["inventory"]["status_counts"].get(key) == value
            for key, value in expected_counts.items()
        )
    assertions.update(_prohibited_assertions(case, actual))
    if "contract_assertions" in actual:
        assertions.update({f"contract.{key}": value for key, value in actual["contract_assertions"].items()})
    if "graph_schema_errors" in actual:
        assertions["sealed_graph_schema"] = not actual["graph_schema_errors"]
        assertions.update({f"projection.{key}": value for key, value in actual["renderer_assertions"].items()})
    failures: list[dict[str, Any]] = []
    for name, passed in assertions.items():
        if passed:
            continue
        detail: dict[str, Any] = {"assertion": name}
        if name == "diagnostic_exact":
            detail.update({"expected": expected["diagnostic"], "actual": actual["diagnostic"]})
        elif name == "coverage_exact":
            detail.update({"expected": expected["coverage"], "actual": actual["coverage"]})
        elif name == "operation_exact":
            detail.update({"expected": expected["operation"], "actual": actual["operation"]})
        elif name == "evidence_kinds_exact":
            detail.update({"expected": expected["evidence_kinds"], "actual": actual["evidence_kinds"]})
        failures.append(detail)
    return assertions, failures


def _golden_case(case: dict[str, Any], repetitions: int) -> tuple[dict[str, Any], dict[str, bool], list[dict[str, Any]]]:
    executions = [golden.execute(case, repetition=index + 1) for index in range(repetitions)]
    actual = executions[0]
    canonical = [canonical_json(strip_volatile(item["graph"])) for item in executions]
    repeatable = all(item == canonical[0] for item in canonical[1:])
    assertions, failures = _compare_expected(case, actual, golden_suite=True)
    assertions["deterministic_repetitions"] = repeatable
    if not repeatable:
        failures.append({"assertion": "deterministic_repetitions"})
    return actual, assertions, failures


def _load_sample_graphs(golden_path: Path | None) -> dict[str, dict[str, Any]]:
    if golden_path is None:
        raise FileNotFoundError("catalog execution requires the materialized golden suite path")
    suite = load_json(golden_path)
    wanted = {"G-001", "G-004", "G-006", "G-015", "G-018", "G-020"}
    return {
        case["id"]: golden.execute(case)["graph"]
        for case in suite["cases"]
        if case["id"] in wanted
    }


def run_suite(
    paths: SuitePaths,
    *,
    selected_ids: set[str] | None = None,
    repetitions: int = 3,
    require_all: bool = False,
) -> dict[str, Any]:
    validation = validate_suite_file(paths)
    if not validation["valid"]:
        return {
            "schema_version": "agent-doctor-test-run/0.1",
            "product_version": __version__,
            "suite": str(paths.suite),
            "evidence_outcome": "execution_failed",
            "gate_outcome": "not_evaluated",
            "counts": {"invalid": validation.get("case_count", 0)},
            "validation": validation,
            "cases": [],
            "qualification_claims": [],
            "measurement_status": "not_performed",
        }
    suite = load_json(paths.suite)
    is_golden = suite["suite_kind"] == "golden"
    samples: dict[str, dict[str, Any]] = {}
    if not is_golden:
        try:
            samples = _load_sample_graphs(paths.golden)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            return {
                "schema_version": "agent-doctor-test-run/0.1",
                "product_version": __version__,
                "suite_id": suite["suite_id"],
                "evidence_outcome": "execution_failed",
                "gate_outcome": "not_evaluated",
                "counts": {"invalid": len(suite["cases"])},
                "validation": validation,
                "runner_error": f"sample graph setup failed: {type(exc).__name__}: {exc}",
                "cases": [],
                "qualification_claims": [],
                "measurement_status": "not_performed",
            }

    records: list[dict[str, Any]] = []
    execution_errors = 0
    available_ids = {case["id"] for case in suite["cases"]}
    missing_requested = sorted((selected_ids or set()) - available_ids)
    for missing_id in missing_requested:
        records.append(
            {
                "id": missing_id,
                "title": "requested scenario is absent",
                "test_type": "unknown",
                "review_status": "unknown",
                "status": "invalid",
                "reason": "requested scenario ID is not present in the suite",
                "assertions": {},
            }
        )
        execution_errors += 1
    for case in suite["cases"]:
        if selected_ids is not None and case["id"] not in selected_ids:
            continue
        record: dict[str, Any] = {
            "id": case["id"],
            "title": case["title"],
            "test_type": case["test_type"],
            "review_status": case["review"]["status"],
        }
        if not is_golden:
            is_supported, reason = catalog.supported(case)
            if not is_supported:
                record.update({"status": "unsupported", "reason": reason, "assertions": {}})
                records.append(record)
                continue
        try:
            if is_golden:
                actual, assertions, failures = _golden_case(case, repetitions)
            else:
                actual = catalog.execute(case, samples)
                assertions, failures = _compare_expected(case, actual, golden_suite=False)
            record.update(
                {
                    "status": "passed" if not failures else "failed",
                    "assertions": assertions,
                    "failures": failures,
                    "actual": {
                        "diagnostic": actual["diagnostic"],
                        "evidence_kinds": actual["evidence_kinds"],
                        "inventory": actual["inventory"],
                        "coverage": actual["coverage"],
                        "operation": actual["operation"],
                        "result_id": actual.get("graph", {}).get("result_id"),
                    },
                }
            )
        except Exception as exc:  # runner boundary: preserve the case and classify tooling failure
            execution_errors += 1
            record.update(
                {
                    "status": "invalid",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "assertions": {},
                }
            )
        records.append(record)

    counts = Counter(item["status"] for item in records)
    if execution_errors or (require_all and counts["unsupported"]):
        evidence_outcome = "execution_failed"
        gate_outcome = "not_evaluated"
    elif counts["failed"]:
        evidence_outcome = "valid"
        gate_outcome = "policy_failed"
    else:
        evidence_outcome = "valid"
        gate_outcome = "satisfied_for_executed_scenarios"
    return {
        "schema_version": "agent-doctor-test-run/0.1",
        "scenario_schema_version": SCENARIO_SCHEMA_VERSION,
        "product_version": __version__,
        "suite_id": suite["suite_id"],
        "suite_version": suite["suite_version"],
        "suite_kind": suite["suite_kind"],
        "repetitions": repetitions if is_golden else 1,
        "require_all": require_all,
        "evidence_outcome": evidence_outcome,
        "gate_outcome": gate_outcome,
        "counts": {key: counts.get(key, 0) for key in ("passed", "failed", "unsupported", "invalid")},
        "validation": validation,
        "cases": records,
        "qualification_claims": [],
        "measurement_status": "not_performed",
        "measurement_note": "This run checks normative scenario contracts only. It does not establish PRD accuracy, usefulness, calibration, or release targets.",
    }


def report_exit_code(report: dict[str, Any]) -> int:
    if report.get("evidence_outcome") == "execution_failed":
        return 3
    if report.get("gate_outcome") == "policy_failed":
        return 2
    return 0
