"""Pure CI policy evaluation over one sealed result graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import stable_id
from .invariants import validate_result_graph
from .types import CIOutcome, CheckState, SEVERITY_RANK
from .version import CI_POLICY_VERSION


@dataclass(frozen=True)
class CIPolicy:
    fail_at_or_above: str = "high"
    minimum_confidence: str | None = None
    required_families: tuple[str, ...] = ("inventory",)
    candidates_block: bool = False

    def __post_init__(self) -> None:
        if self.fail_at_or_above not in SEVERITY_RANK:
            raise ValueError(f"unknown severity threshold: {self.fail_at_or_above}")
        if self.minimum_confidence not in {None, "low", "medium", "high"}:
            raise ValueError(f"unknown confidence threshold: {self.minimum_confidence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fail_at_or_above": self.fail_at_or_above,
            "minimum_confidence": self.minimum_confidence,
            "required_families": list(self.required_families),
            "candidates_block": self.candidates_block,
        }


def evaluate_ci(graph: dict[str, Any], policy: CIPolicy) -> dict[str, Any]:
    """Evaluate policy without filtering or mutating the durable graph."""

    reasons: list[dict[str, Any]] = []
    blocking_cases: list[str] = []
    invariant_errors = validate_result_graph(graph, require_sealed=True)
    if invariant_errors or graph.get("run", {}).get("outcome") == "execution_failed":
        reasons.extend(
            {"code": "invalid_or_unsealed_result", "path": item.path, "detail": item.message}
            for item in invariant_errors
        )
        if not reasons:
            reasons.append({"code": "result_execution_failed"})
        outcome = CIOutcome.EXECUTION_FAILED.value
    else:
        family_rows = {item["family"]: item for item in graph.get("coverage", {}).get("by_family", [])}
        for family in policy.required_families:
            row = family_rows.get(family)
            if row is None:
                reasons.append({"code": "required_family_missing", "family": family})
            elif (
                row.get("error", 0)
                or row.get("not_run", 0)
                or row.get("abstained", 0)
                or row.get("completed", 0) < row.get("attempted", 0)
            ):
                reasons.append({"code": "required_family_incomplete", "family": family, "coverage": row})
        if reasons:
            outcome = CIOutcome.EXECUTION_FAILED.value
        else:
            confidence_rank = {"low": 0, "medium": 1, "high": 2}
            minimum_confidence_rank = (
                confidence_rank[policy.minimum_confidence]
                if policy.minimum_confidence is not None
                else -1
            )
            threshold_rank = SEVERITY_RANK[policy.fail_at_or_above]
            for case in graph.get("interaction_cases", []):
                is_blockable = case.get("state") == CheckState.FINDING.value or (
                    policy.candidates_block and case.get("state") == CheckState.CANDIDATE.value
                )
                severity = case.get("severity") if case.get("state") == CheckState.FINDING.value else case.get("potential_severity")
                confidence = case.get("confidence")
                if (
                    is_blockable
                    and severity in SEVERITY_RANK
                    and SEVERITY_RANK[severity] >= threshold_rank
                    and confidence in confidence_rank
                    and confidence_rank[confidence] >= minimum_confidence_rank
                ):
                    blocking_cases.append(case["case_id"])
            if blocking_cases:
                outcome = CIOutcome.POLICY_FAILED.value
                reasons.append(
                    {
                        "code": "finding_threshold_exceeded",
                        "threshold": policy.fail_at_or_above,
                        "case_count": len(blocking_cases),
                    }
                )
            else:
                outcome = CIOutcome.SATISFIED.value

    decision = {
        "schema_version": "agent-doctor-ci-decision/0.1",
        "policy_version": CI_POLICY_VERSION,
        "result_ref": graph.get("result_id"),
        "outcome": outcome,
        "policy": policy.to_dict(),
        "blocking_case_refs": sorted(blocking_cases),
        "reasons": reasons,
        "durable_case_count": len(graph.get("interaction_cases", [])),
    }
    decision["decision_id"] = stable_id("ci", decision)
    return decision


def exit_code(decision: dict[str, Any]) -> int:
    return {
        CIOutcome.SATISFIED.value: 0,
        CIOutcome.POLICY_FAILED.value: 2,
        CIOutcome.EXECUTION_FAILED.value: 3,
    }[decision["outcome"]]
