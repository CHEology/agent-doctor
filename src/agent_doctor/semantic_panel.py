"""Deterministic planning and local policy for the bounded semantic panel."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Mapping, Sequence

from .canonical import stable_id


MAX_PANEL_QUESTIONS = 32
MAX_QUESTIONS_PER_PAIR = 4

DIMENSION_PRIORITY = (
    "trigger",
    "question_policy",
    "required_action",
    "output_form",
    "applicability",
    "artifact_handling",
    "tool_policy",
    "general",
)

RECOMMENDATION_KINDS = frozenset(
    {
        "clarify_trigger",
        "add_negative_trigger",
        "split_responsibility",
        "declare_primary_handler",
        "add_boundary_example",
        "add_eval_fixture",
        "no_action",
    }
)

RECOMMENDATION_COMPATIBILITY = {
    "semantic_conflict": frozenset(
        {
            "clarify_trigger",
            "split_responsibility",
            "declare_primary_handler",
            "add_boundary_example",
            "add_eval_fixture",
            "no_action",
        }
    ),
    "scope_overlap": frozenset(
        {
            "clarify_trigger",
            "add_negative_trigger",
            "split_responsibility",
            "declare_primary_handler",
            "add_boundary_example",
            "add_eval_fixture",
            "no_action",
        }
    ),
    "behavioral_redundancy": frozenset(
        {
            "split_responsibility",
            "declare_primary_handler",
            "add_boundary_example",
            "add_eval_fixture",
            "no_action",
        }
    ),
    "complementarity": frozenset(
        {"add_boundary_example", "add_eval_fixture", "no_action"}
    ),
    "no_material_relation": frozenset({"add_eval_fixture", "no_action"}),
}


def _claims_by_dimension(handle: Mapping[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for claim in handle.get("claims", []):
        if not isinstance(claim, dict):
            continue
        dimension = claim.get("dimension")
        claim_ref = claim.get("claim_ref")
        if isinstance(dimension, str) and isinstance(claim_ref, str):
            grouped.setdefault(dimension, []).append(claim_ref)
    return {key: sorted(set(value)) for key, value in grouped.items()}


def _dimension_order(value: str) -> tuple[int, str]:
    try:
        return DIMENSION_PRIORITY.index(value), value
    except ValueError:
        return len(DIMENSION_PRIORITY), value


def plan_semantic_questions(
    handles: Sequence[Mapping[str, Any]],
    *,
    max_questions: int = MAX_PANEL_QUESTIONS,
) -> dict[str, Any]:
    """Freeze bounded pair/dimension questions and disclose any truncation."""

    if max_questions < 1:
        raise ValueError("semantic question limit must be positive")
    ordered_handles = sorted(handles, key=lambda item: str(item.get("source_ref", "")))
    eligible: list[dict[str, Any]] = []
    eligible_pairs: set[tuple[str, str]] = set()
    for first, second in combinations(ordered_handles, 2):
        first_ref = str(first["source_ref"])
        second_ref = str(second["source_ref"])
        pair = (first_ref, second_ref)
        eligible_pairs.add(pair)
        first_claims = _claims_by_dimension(first)
        second_claims = _claims_by_dimension(second)
        shared = sorted(set(first_claims).intersection(second_claims), key=_dimension_order)
        if not shared:
            shared = ["cross_dimension"]
        for dimension in shared[:MAX_QUESTIONS_PER_PAIR]:
            if dimension == "cross_dimension":
                claim_refs = sorted(
                    {
                        *[item for values in first_claims.values() for item in values],
                        *[item for values in second_claims.values() for item in values],
                    }
                )[:8]
            else:
                claim_refs = sorted(
                    {*first_claims[dimension], *second_claims[dimension]}
                )
            identity = {
                "source_refs": pair,
                "dimension": dimension,
                "claim_refs": claim_refs,
                "planner": "agent-doctor-semantic-question-planner/0.1",
            }
            eligible.append(
                {
                    "question_id": stable_id("semantic-question", identity),
                    "source_refs": list(pair),
                    "handle_refs": [str(first["handle_id"]), str(second["handle_id"])],
                    "claim_refs": claim_refs,
                    "dimension": dimension,
                    "question": (
                        "Using only the cited static excerpts, classify the material "
                        f"relationship between these two Skills on {dimension}. "
                        "Keep conflict, overlap, redundancy, and complementarity "
                        "independent; do not infer runtime selection or causality."
                    ),
                    "region_basis": {
                        "first_effective_scope": first.get("effective_scope", {"state": "unknown"}),
                        "second_effective_scope": second.get("effective_scope", {"state": "unknown"}),
                        "runtime_observed": False,
                    },
                }
            )
    eligible.sort(
        key=lambda item: (
            tuple(item["source_refs"]),
            _dimension_order(str(item["dimension"])),
            str(item["question_id"]),
        )
    )
    # Round-robin pairs before taking the global bound so a large inventory is
    # not silently dominated by the first lexicographic Skill pair.
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in eligible:
        source_pair = (
            str(item["source_refs"][0]),
            str(item["source_refs"][1]),
        )
        by_pair.setdefault(source_pair, []).append(item)
    remaining_pairs = set(by_pair)
    pair_use: dict[str, int] = {}
    pair_order: list[tuple[str, str]] = []
    while remaining_pairs:
        pair = min(
            remaining_pairs,
            key=lambda value: (
                pair_use.get(value[0], 0) + pair_use.get(value[1], 0),
                max(pair_use.get(value[0], 0), pair_use.get(value[1], 0)),
                value,
            ),
        )
        remaining_pairs.remove(pair)
        pair_order.append(pair)
        pair_use[pair[0]] = pair_use.get(pair[0], 0) + 1
        pair_use[pair[1]] = pair_use.get(pair[1], 0) + 1
    interleaved: list[dict[str, Any]] = []
    for offset in range(MAX_QUESTIONS_PER_PAIR):
        for pair in pair_order:
            if offset < len(by_pair[pair]):
                interleaved.append(by_pair[pair][offset])
    eligible = interleaved
    questions = eligible[:max_questions]
    planned_pairs = {
        tuple(str(value) for value in item["source_refs"]) for item in questions
    }
    return {
        "planner_version": "agent-doctor-semantic-question-planner/0.1",
        "questions": questions,
        "coverage": {
            "eligible_pair_count": len(eligible_pairs),
            "planned_pair_count": len(planned_pairs),
            "eligible_question_count": len(eligible),
            "emitted_question_count": len(questions),
            "omitted_question_count": len(eligible) - len(questions),
            "complete": len(eligible) == len(questions),
            "question_limit": max_questions,
            "omission_reason": (
                None
                if len(eligible) == len(questions)
                else "bounded_semantic_question_limit"
            ),
        },
    }


def recommendation_is_compatible(label: str, kind: str) -> bool:
    """Return whether a model proposal may become a manual local action."""

    return (
        kind in RECOMMENDATION_KINDS
        and kind in RECOMMENDATION_COMPATIBILITY.get(label, frozenset())
    )


def adjudicate_panel_answer(
    answer: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply the closed local state/severity table to one validated panel join."""

    label = str(answer.get("label", ""))
    agreement = (
        review.get("disposition") == "corroborated"
        and review.get("label") == label
    )
    challenged = review.get("disposition") == "challenged"
    counterexample_open = any(
        item.get("status") != "excluded"
        for item in (answer.get("counterexample", {}), review.get("counterexample", {}))
        if isinstance(item, Mapping)
    )
    missing_evidence = bool(answer.get("missing_evidence")) or bool(
        review.get("missing_evidence")
    )
    decisive = agreement and not counterexample_open and not missing_evidence
    result: dict[str, Any] = {
        "state": "insufficient_evidence",
        "labels": [],
        "severity": None,
        "potential_severity": None,
        "confidence": "low",
        "runtime_validation_needed": False,
        "agreement": agreement,
        "challenged": challenged,
        "decisive": decisive,
        "counterexample_open": counterexample_open,
        "missing_evidence": missing_evidence,
    }
    if challenged:
        return result
    if not decisive:
        if label in {"semantic_conflict", "scope_overlap"}:
            result.update(
                {
                    "state": "candidate",
                    "labels": [label],
                    "potential_severity": (
                        "high" if label == "semantic_conflict" else "medium"
                    ),
                    "runtime_validation_needed": label == "scope_overlap",
                }
            )
        return result
    if label == "semantic_conflict":
        result.update(
            {"state": "finding", "labels": [label], "severity": "high", "confidence": "medium"}
        )
    elif label == "behavioral_redundancy":
        result.update(
            {"state": "finding", "labels": [label], "severity": "medium", "confidence": "medium"}
        )
    elif label == "scope_overlap":
        result.update(
            {
                "state": "candidate",
                "labels": [label],
                "potential_severity": "medium",
                "confidence": "medium",
                "runtime_validation_needed": True,
            }
        )
    else:
        result.update(
            {"state": "pass", "labels": [label], "severity": "info", "confidence": "medium"}
        )
    return result
