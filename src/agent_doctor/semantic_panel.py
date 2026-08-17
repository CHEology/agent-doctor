"""Deterministic planning and local policy for the bounded semantic panel."""

from __future__ import annotations

from itertools import combinations
import re
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

TOKEN = re.compile(r"[a-z0-9][a-z0-9_.+-]*|[\u3400-\u9fff]+", re.IGNORECASE)
STOP_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "codex",
        "for",
        "from",
        "if",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "skill",
        "skills",
        "that",
        "the",
        "this",
        "to",
        "use",
        "user",
        "when",
        "with",
    }
)


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


def _retrieval_tokens(handle: Mapping[str, Any], dimension: str) -> set[str]:
    tokens: set[str] = set()
    for claim in handle.get("claims", []):
        if not isinstance(claim, Mapping):
            continue
        if dimension != "cross_dimension" and claim.get("dimension") != dimension:
            continue
        excerpt = claim.get("excerpt")
        if not isinstance(excerpt, str):
            continue
        for raw in TOKEN.findall(excerpt.casefold()):
            raw = raw.strip("._+-")
            if raw in STOP_TOKENS:
                continue
            if re.fullmatch(r"[\u3400-\u9fff]+", raw):
                if len(raw) == 1:
                    tokens.add(raw)
                else:
                    tokens.update(raw[index : index + 2] for index in range(len(raw) - 1))
            elif len(raw) > 1 and not raw.isdigit():
                tokens.add(raw)
    location = str(handle.get("location", "")).casefold()
    skill_name = location.rstrip("/").split("/")[-2] if "/" in location else location
    tokens.update(
        item
        for item in re.split(r"[^a-z0-9\u3400-\u9fff]+", skill_name)
        if len(item) > 1 and not item.isdigit() and item not in STOP_TOKENS
    )
    return tokens


def _modalities(handle: Mapping[str, Any], dimension: str) -> set[str]:
    return {
        str(claim.get("modality"))
        for claim in handle.get("claims", [])
        if isinstance(claim, Mapping)
        and (dimension == "cross_dimension" or claim.get("dimension") == dimension)
        and isinstance(claim.get("modality"), str)
    }


def _retrieval_basis(
    first: Mapping[str, Any], second: Mapping[str, Any], dimension: str
) -> dict[str, Any]:
    first_tokens = _retrieval_tokens(first, dimension)
    second_tokens = _retrieval_tokens(second, dimension)
    shared = sorted(first_tokens.intersection(second_tokens))
    union = first_tokens.union(second_tokens)
    minimum = min(len(first_tokens), len(second_tokens))
    jaccard_milli = (1000 * len(shared) // len(union)) if union else 0
    containment_milli = (1000 * len(shared) // minimum) if minimum else 0
    first_modalities = _modalities(first, dimension)
    second_modalities = _modalities(second, dimension)
    modality_contrast = (
        "required" in first_modalities
        and "forbidden" in second_modalities
        or "forbidden" in first_modalities
        and "required" in second_modalities
    )
    score = (
        jaccard_milli * 100
        + containment_milli * 30
        + min(len(shared), 20) * 25
        + (50_000 if modality_contrast and shared else 0)
        + (2_000 if dimension == "trigger" and shared else 0)
    )
    return {
        "method": "deterministic_lexical_candidate_retrieval/0.1",
        "score": score,
        "shared_tokens": shared[:12],
        "shared_token_count": len(shared),
        "jaccard_milli": jaccard_milli,
        "containment_milli": containment_milli,
        "modality_contrast": modality_contrast,
        "meaning": "retrieval priority only; not a relationship label or severity",
    }


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
            retrieval = _retrieval_basis(first, second, dimension)
            identity = {
                "source_refs": pair,
                "dimension": dimension,
                "claim_refs": claim_refs,
                "planner": "agent-doctor-semantic-question-planner/0.2",
                "retrieval": retrieval,
            }
            eligible.append(
                {
                    "question_id": stable_id("semantic-question", identity),
                    "source_refs": list(pair),
                    "handle_refs": [str(first["handle_id"]), str(second["handle_id"])],
                    "claim_refs": claim_refs,
                    "dimension": dimension,
                    "retrieval": retrieval,
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
            -int(item["retrieval"]["score"]),
            _dimension_order(str(item["dimension"])),
            tuple(item["source_refs"]),
            str(item["question_id"]),
        )
    )
    # Retrieve the most textually relevant pairs before model judgment. For
    # equal scores, balance source use so a large inventory is not silently
    # dominated by one Skill. This score selects questions only; it never
    # becomes a relationship label, severity, confidence, or finding.
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in eligible:
        source_pair = (
            str(item["source_refs"][0]),
            str(item["source_refs"][1]),
        )
        by_pair.setdefault(source_pair, []).append(item)
    for pair in by_pair:
        by_pair[pair].sort(
            key=lambda item: (
                -int(item["retrieval"]["score"]),
                _dimension_order(str(item["dimension"])),
                str(item["question_id"]),
            )
        )
    remaining_pairs = set(by_pair)
    pair_use: dict[str, int] = {}
    pair_order: list[tuple[str, str]] = []
    while remaining_pairs:
        pair = min(
            remaining_pairs,
            key=lambda value: (
                -int(by_pair[value][0]["retrieval"]["score"]),
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
        "planner_version": "agent-doctor-semantic-question-planner/0.2",
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


def adjudicate_panel_answers(
    analyst_a: Mapping[str, Any],
    analyst_b: Mapping[str, Any],
    judgment: Mapping[str, Any],
    *,
    shared_region_established: bool = True,
) -> dict[str, Any]:
    """Apply the closed local table to two blind answers and one judgment."""

    analyst_agreement = analyst_a.get("label") == analyst_b.get("label")
    label = str(judgment.get("selected_label") or "")
    consensus = (
        judgment.get("disposition") == "corroborated_consensus"
        and analyst_agreement
        and label == analyst_a.get("label")
    )
    resolved_disagreement = (
        judgment.get("disposition") == "resolved_disagreement"
        and not analyst_agreement
        and label in {analyst_a.get("label"), analyst_b.get("label")}
    )
    challenged = judgment.get("disposition") == "challenged"
    counterexample_open = any(
        item.get("status") != "excluded"
        for item in (
            analyst_a.get("counterexample", {}),
            analyst_b.get("counterexample", {}),
            judgment.get("counterexample", {}),
        )
        if isinstance(item, Mapping)
    )
    missing_evidence = any(
        bool(item.get("missing_evidence"))
        for item in (analyst_a, analyst_b, judgment)
    )
    decisive = consensus and not counterexample_open and not missing_evidence
    result: dict[str, Any] = {
        "state": "insufficient_evidence",
        "labels": [],
        "severity": None,
        "potential_severity": None,
        "confidence": "low",
        "runtime_validation_needed": False,
        "agreement": consensus,
        "analyst_agreement": analyst_agreement,
        "resolved_disagreement": resolved_disagreement,
        "resolution_kind": (
            "consensus"
            if consensus
            else "judge_resolution"
            if resolved_disagreement
            else "abstained"
        ),
        "challenged": challenged,
        "decisive": decisive,
        "counterexample_open": counterexample_open,
        "missing_evidence": missing_evidence,
    }
    if challenged or judgment.get("disposition") == "insufficient":
        return result
    if resolved_disagreement:
        if label in {"semantic_conflict", "scope_overlap", "behavioral_redundancy"}:
            result.update(
                {
                    "state": "candidate",
                    "labels": [label],
                    "potential_severity": (
                        "high" if label == "semantic_conflict" else "medium"
                    ),
                    "confidence": "low",
                    "runtime_validation_needed": label
                    in {"semantic_conflict", "scope_overlap", "behavioral_redundancy"},
                }
            )
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
    if label == "semantic_conflict" and not shared_region_established:
        result.update(
            {
                "state": "candidate",
                "labels": [label],
                "potential_severity": "high",
                "confidence": "medium",
                "runtime_validation_needed": True,
            }
        )
    elif label == "semantic_conflict":
        result.update(
            {"state": "finding", "labels": [label], "severity": "high", "confidence": "medium"}
        )
    elif label == "behavioral_redundancy" and not shared_region_established:
        result.update(
            {
                "state": "candidate",
                "labels": [label],
                "potential_severity": "medium",
                "confidence": "medium",
                "runtime_validation_needed": True,
            }
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


def adjudicate_panel_answer(
    answer: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    shared_region_established: bool = True,
) -> dict[str, Any]:
    """Compatibility wrapper for the retired one-analyst/critic contract."""

    peer = dict(answer)
    peer["label"] = review.get("label")
    peer["counterexample"] = review.get("counterexample", {})
    peer["missing_evidence"] = review.get("missing_evidence", [])
    disposition = str(review.get("disposition", "insufficient"))
    judgment = {
        "selected_label": (
            answer.get("label") if disposition == "corroborated" else None
        ),
        "disposition": (
            "corroborated_consensus"
            if disposition == "corroborated"
            else "challenged"
            if disposition == "challenged"
            else "insufficient"
        ),
        "counterexample": review.get("counterexample", {}),
        "missing_evidence": review.get("missing_evidence", []),
    }
    return adjudicate_panel_answers(
        answer,
        peer,
        judgment,
        shared_region_established=shared_region_established,
    )
