"""Sealing-time invariants for the canonical product result graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import (
    CheckState,
    Confidence,
    EvidenceKind,
    RunOutcome,
    Severity,
    SUBSTANTIVE_LABELS,
    VALIDATION_QUALIFIERS,
)
from .version import RESULT_SCHEMA_VERSION


@dataclass(frozen=True)
class InvariantError:
    path: str
    message: str


def validate_result_graph(graph: dict[str, Any], *, require_sealed: bool = True) -> list[InvariantError]:
    errors: list[InvariantError] = []

    def fail(path: str, message: str) -> None:
        errors.append(InvariantError(path, message))

    if graph.get("schema_version") != RESULT_SCHEMA_VERSION:
        fail("schema_version", f"must equal {RESULT_SCHEMA_VERSION}")
    if require_sealed and graph.get("sealed") is not True:
        fail("sealed", "canonical result must be sealed")
    if graph.get("run", {}).get("outcome") not in {item.value for item in RunOutcome}:
        fail("run.outcome", "unknown run outcome")

    source_ids = [item.get("source_id") for item in graph.get("inventory", {}).get("sources", [])]
    claim_ids = [item.get("claim_id") for item in graph.get("claims", [])]
    evidence_ids = [item.get("evidence_id") for item in graph.get("evidence", [])]
    check_ids = [item.get("execution_id") for item in graph.get("checks", [])]
    case_ids = [item.get("case_id") for item in graph.get("interaction_cases", [])]
    action_ids = [item.get("action_id") for item in graph.get("next_actions", [])]
    for path, values in (
        ("inventory.sources", source_ids),
        ("claims", claim_ids),
        ("evidence", evidence_ids),
        ("checks", check_ids),
        ("interaction_cases", case_ids),
        ("next_actions", action_ids),
    ):
        if None in values or len(values) != len(set(values)):
            fail(path, "identifiers must be present and unique")

    source_set, claim_set = set(source_ids), set(claim_ids)
    evidence_set, check_set = set(evidence_ids), set(check_ids)
    case_set, action_set = set(case_ids), set(action_ids)
    evidence_by_id = {item.get("evidence_id"): item for item in graph.get("evidence", [])}
    checks_by_id = {item.get("execution_id"): item for item in graph.get("checks", [])}

    for index, claim in enumerate(graph.get("claims", [])):
        if claim.get("source_ref") not in source_set:
            fail(f"claims[{index}].source_ref", "must reference an inventoried source")

    for index, evidence in enumerate(graph.get("evidence", [])):
        kind = evidence.get("kind")
        if kind not in {item.value for item in EvidenceKind}:
            fail(f"evidence[{index}].kind", "unknown evidence kind")
        for source_ref in evidence.get("source_refs", []):
            if source_ref not in source_set:
                fail(f"evidence[{index}].source_refs", "unknown source reference")
        for parent in evidence.get("parent_evidence_refs", []):
            if parent not in evidence_set:
                fail(f"evidence[{index}].parent_evidence_refs", "unknown parent evidence")
        if kind == EvidenceKind.DERIVED.value and not evidence.get("parent_evidence_refs"):
            fail(f"evidence[{index}]", "derived evidence requires parent lineage")
        if kind == EvidenceKind.INFERRED.value:
            if not evidence.get("rule_or_provider"):
                fail(f"evidence[{index}]", "inferred evidence requires provider or inference attribution")
            if not evidence.get("parent_evidence_refs"):
                fail(f"evidence[{index}]", "inferred evidence requires cited parent lineage")

    # Evidence is append-only conceptually, but canonical ordering is by ID;
    # validate the graph itself rather than relying on array position.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_evidence(evidence_id: str) -> None:
        if evidence_id in visited:
            return
        if evidence_id in visiting:
            fail("evidence", f"lineage cycle includes {evidence_id}")
            return
        visiting.add(evidence_id)
        for parent in evidence_by_id.get(evidence_id, {}).get("parent_evidence_refs", []):
            if parent in evidence_by_id:
                visit_evidence(parent)
        visiting.remove(evidence_id)
        visited.add(evidence_id)

    for evidence_id in evidence_ids:
        visit_evidence(evidence_id)

    valid_states = {item.value for item in CheckState}
    for index, check in enumerate(graph.get("checks", [])):
        if check.get("state") not in valid_states:
            fail(f"checks[{index}].state", "unknown or test-only check state")
        for evidence_ref in check.get("evidence_refs", []):
            if evidence_ref not in evidence_set:
                fail(f"checks[{index}].evidence_refs", "unknown evidence reference")

    valid_severity = {item.value for item in Severity}
    valid_confidence = {item.value for item in Confidence}
    exclusive_labels = {"semantic_conflict", "behavioral_redundancy", "complementarity"}
    for index, case in enumerate(graph.get("interaction_cases", [])):
        path = f"interaction_cases[{index}]"
        if case.get("check_ref") not in check_set:
            fail(f"{path}.check_ref", "unknown check reference")
        check_state = checks_by_id.get(case.get("check_ref"), {}).get("state")
        if case.get("state") != check_state:
            fail(f"{path}.state", "case state must equal its check state")
        if case.get("state") not in valid_states:
            fail(f"{path}.state", "unknown check state")
        for source_ref in case.get("source_refs", []):
            if source_ref not in source_set:
                fail(f"{path}.source_refs", "unknown source reference")
        for claim_ref in case.get("claim_refs", []):
            if claim_ref not in claim_set:
                fail(f"{path}.claim_refs", "unknown claim reference")
        for evidence_ref in case.get("evidence_refs", []):
            if evidence_ref not in evidence_set:
                fail(f"{path}.evidence_refs", "unknown evidence reference")
        for action_ref in case.get("next_action_refs", []):
            if action_ref not in action_set:
                fail(f"{path}.next_action_refs", "unknown next-action reference")

        severity = case.get("severity")
        potential = case.get("potential_severity")
        confidence = case.get("confidence")
        if severity is not None and severity not in valid_severity:
            fail(f"{path}.severity", "unknown severity")
        if potential is not None and potential not in valid_severity:
            fail(f"{path}.potential_severity", "unknown potential severity")
        if confidence is not None and confidence not in valid_confidence:
            fail(f"{path}.confidence", "unknown confidence")
        if case.get("state") in {CheckState.NOT_RUN.value, CheckState.ERROR.value}:
            if case.get("assessments") or severity is not None or potential is not None or confidence is not None:
                fail(path, "not_run/error cannot carry a substantive label, severity, potential severity, or confidence")
        if case.get("state") == CheckState.INSUFFICIENT_EVIDENCE.value and severity is not None:
            fail(f"{path}.severity", "abstention cannot invent assigned severity")
        if case.get("state") == CheckState.CANDIDATE.value and severity is not None:
            fail(f"{path}.severity", "candidate uses potential severity, not assigned severity")
        if case.get("state") == CheckState.FINDING.value:
            if not case.get("assessments"):
                fail(f"{path}.assessments", "finding requires a substantive assessment")
            if severity is None or confidence is None:
                fail(path, "finding requires assigned severity and confidence")
            if potential is not None:
                fail(f"{path}.potential_severity", "finding cannot retain candidate-only potential severity")
            if not case.get("next_action_refs"):
                fail(f"{path}.next_action_refs", "finding requires a bounded next action")
        if case.get("state") == CheckState.CANDIDATE.value and (potential is None or confidence is None):
            fail(path, "candidate requires potential severity and confidence")
        if case.get("state") == CheckState.INSUFFICIENT_EVIDENCE.value and confidence is None:
            fail(f"{path}.confidence", "abstention requires confidence in the abstention decision")

        keyed_labels: dict[tuple[tuple[str, ...], str, str], set[str]] = {}
        for assessment_index, assessment in enumerate(case.get("assessments", [])):
            label = assessment.get("label")
            assessment_path = f"{path}.assessments[{assessment_index}]"
            if label not in SUBSTANTIVE_LABELS:
                fail(f"{assessment_path}.label", "unknown label or state in label field")
            if assessment.get("region_ref") != case.get("region_ref"):
                fail(f"{assessment_path}.region_ref", "assessment must retain the case applicability region")
            for claim_ref in assessment.get("claim_refs", []):
                if claim_ref not in claim_set:
                    fail(f"{assessment_path}.claim_refs", "unknown claim reference")
            key = (
                tuple(sorted(assessment.get("claim_refs", []))),
                assessment.get("region_ref", ""),
                assessment.get("dimension_ref", ""),
            )
            keyed_labels.setdefault(key, set()).add(label)
            if assessment.get("status") == "active" and label == "semantic_conflict":
                if any(
                    other.get("label") == "precedence_override"
                    and other.get("status") == "resolved"
                    and other.get("dimension_ref") == assessment.get("dimension_ref")
                    for other in case.get("assessments", [])
                ):
                    fail(assessment_path, "resolved override cannot retain an active conflict")
        for key, labels in keyed_labels.items():
            if len(labels & exclusive_labels) > 1:
                fail(path, f"mutually exclusive labels share one claim/region/dimension key: {sorted(labels)}")

        for qualifier_index, qualifier in enumerate(case.get("validation_qualifiers", [])):
            if qualifier.get("kind") not in VALIDATION_QUALIFIERS:
                fail(f"{path}.validation_qualifiers[{qualifier_index}]", "unknown qualifier")
            if not qualifier.get("proposition") or not qualifier.get("confirm_condition") or not qualifier.get("refute_condition"):
                fail(f"{path}.validation_qualifiers[{qualifier_index}]", "runtime qualifier must be falsifiable")
            if case.get("state") != CheckState.CANDIDATE.value:
                fail(f"{path}.validation_qualifiers[{qualifier_index}]", "runtime qualifier is valid only on a candidate")

    for index, group in enumerate(graph.get("finding_groups", [])):
        members = group.get("member_case_refs", [])
        if not members or any(member not in case_set for member in members):
            fail(f"finding_groups[{index}].member_case_refs", "group members must be known and non-empty")
        if len(members) != len(set(members)):
            fail(f"finding_groups[{index}].member_case_refs", "group membership must be lossless and unique")
        member_states = {
            item.get("state")
            for item in graph.get("interaction_cases", [])
            if item.get("case_id") in members
        }
        if member_states - {CheckState.FINDING.value, CheckState.CANDIDATE.value}:
            fail(f"finding_groups[{index}].member_case_refs", "only findings and candidates may enter finding groups")

    # A provider can corroborate only inferred evidence; it cannot retype it.
    for evidence_id, evidence in evidence_by_id.items():
        attribution = evidence.get("rule_or_provider", {})
        if attribution.get("source_kind") == "model" and evidence.get("kind") != EvidenceKind.INFERRED.value:
            fail(f"evidence[{evidence_id}].kind", "model-origin evidence must remain inferred")

    return errors
