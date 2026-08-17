"""Conservative human-facing views derived from a sealed result graph.

This module is a projection only.  It never changes case state, labels,
severity, confidence, applicability, or evidence provenance.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


ATTENTION_STATES = frozenset({"finding", "candidate"})
UNKNOWN_STATES = frozenset({"not_run", "insufficient_evidence"})


def _source_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["source_id"]): item
        for item in graph.get("inventory", {}).get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }


def _action_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["action_id"]): item
        for item in graph.get("next_actions", [])
        if isinstance(item, dict) and isinstance(item.get("action_id"), str)
    }


def _labels(case: Mapping[str, Any]) -> list[str]:
    return sorted(
        str(item["label"])
        for item in case.get("assessments", [])
        if isinstance(item, dict) and item.get("label")
    )


def _case_locations(
    case: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    return [
        str(sources[source_ref].get("location", source_ref))
        for source_ref in case.get("source_refs", [])
        if source_ref in sources
    ]


def _case_actions(
    case: Mapping[str, Any], actions: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    return [
        str(actions[action_ref]["summary"])
        for action_ref in case.get("next_action_refs", [])
        if action_ref in actions
    ]


def _case_reason(case: Mapping[str, Any]) -> str:
    labels = _labels(case)
    if labels:
        return "Detected relationship: " + ", ".join(
            label.replace("_", " ") for label in labels
        )
    return str(case.get("question", "No explanatory question was recorded."))


def build_health_cards(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build per-Skill cards without inventing a whole-Skill health verdict."""

    sources = _source_map(graph)
    cases = [
        item
        for item in graph.get("interaction_cases", [])
        if isinstance(item, dict)
    ]
    claims = [
        item for item in graph.get("claims", []) if isinstance(item, dict)
    ]
    cards: list[dict[str, Any]] = []
    for source_ref, source in sorted(
        sources.items(), key=lambda item: str(item[1].get("location", ""))
    ):
        if source.get("type") != "skill_body":
            continue
        related = [item for item in cases if source_ref in item.get("source_refs", [])]
        states = Counter(str(item.get("state")) for item in related)
        labels = sorted({label for item in related for label in _labels(item)})
        dimensions = sorted(
            {
                str(item.get("dimension_ref"))
                for item in related
                if item.get("dimension_ref")
            }
        )
        if source.get("status") in {"unreadable", "truncated", "missing"}:
            status = "unknown"
            explanation = "The Skill body was not read completely."
        elif any(item.get("state") == "error" for item in related):
            status = "error"
            explanation = "At least one attempted check failed to execute."
        elif any(item.get("state") == "finding" for item in related):
            status = "attention"
            explanation = "At least one checked interaction is a finding."
        elif any(item.get("state") == "candidate" for item in related):
            status = "review_candidate"
            explanation = "At least one checked interaction needs bounded validation."
        elif any(item.get("state") in UNKNOWN_STATES for item in related):
            status = "unknown"
            explanation = "At least one relevant check was not completed decisively."
        elif source.get("effective_scope", {}).get("state") == "inapplicable":
            status = "not_applicable"
            explanation = "The Skill is inventoried but not applicable in this frozen scope."
        else:
            status = "no_issue_in_checked_scope"
            explanation = (
                "No issue was emitted for this Skill by the checks that completed; "
                "this is not a universal correctness claim."
            )
        source_claims = [item for item in claims if item.get("source_ref") == source_ref]
        reference_cases = [
            item for item in related if "invalid_reference" in _labels(item)
        ]
        semantic_cases = [
            item
            for item in related
            if str(item.get("question", "")).startswith(
                "What material semantic relationship"
            )
        ]
        health_dimensions = {
            "discovery_and_readability": (
                "checked"
                if source.get("status") == "discovered"
                and source.get("readability") == "readable"
                else "attention"
            ),
            "parsed_behavioral_contract": (
                "checked" if source_claims else "insufficient_evidence"
            ),
            "reference_integrity": (
                "attention"
                if reference_cases
                else "checked_no_issue"
                if any(item.get("kind") == "reference" for item in source_claims)
                else "not_applicable"
            ),
            "cross_skill_interactions": (
                "attention"
                if any(item.get("state") in ATTENTION_STATES for item in related)
                else "checked_no_issue"
                if related
                else "not_completed"
            ),
            "semantic_relationships": (
                "checked"
                if semantic_cases
                and all(item.get("state") not in {"not_run", "error"} for item in semantic_cases)
                else "not_completed"
            ),
            "maintenance_freshness": "not_implemented",
        }
        cards.append(
            {
                "source_ref": source_ref,
                "location": source.get("location"),
                "status": status,
                "explanation": explanation,
                "case_counts": dict(sorted(states.items())),
                "labels": labels,
                "dimensions": dimensions,
                "health_dimensions": health_dimensions,
                "semantic_evaluation": health_dimensions["semantic_relationships"],
                "maintenance_evaluation": "not_implemented",
            }
        )
    return cards


def build_human_summary(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return an answer-first, lossless summary linked to durable graph IDs."""

    sources = _source_map(graph)
    actions = _action_map(graph)
    cases = [
        item
        for item in graph.get("interaction_cases", [])
        if isinstance(item, dict)
    ]
    issues: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    for case in cases:
        item = {
            "case_id": case.get("case_id"),
            "check_ref": case.get("check_ref"),
            "state": case.get("state"),
            "question": case.get("question"),
            "labels": _labels(case),
            "impact": case.get("severity") or case.get("potential_severity"),
            "confidence": case.get("confidence"),
            "locations": _case_locations(case, sources),
            "why": _case_reason(case),
            "recommendations": _case_actions(case, actions),
            "counterexample": case.get("counterexample"),
            "evidence_refs": list(case.get("evidence_refs", [])),
        }
        if case.get("state") in ATTENTION_STATES:
            issues.append(item)
        elif case.get("state") in UNKNOWN_STATES or case.get("state") == "error":
            unknowns.append(item)

    cards = build_health_cards(graph)
    card_counts = Counter(str(item["status"]) for item in cards)
    if not graph.get("sealed") or graph.get("run", {}).get("outcome") == "execution_failed":
        verdict = "The diagnostic did not complete reliably."
    elif issues:
        verdict = f"Review {len(issues)} issue or candidate before treating this Skill set as clean."
    elif unknowns:
        verdict = "No confirmed issue was emitted, but important checks remain incomplete."
    else:
        verdict = "No issue was emitted in the checks that completed."

    return {
        "verdict": verdict,
        "issues": issues,
        "unknowns": unknowns,
        "health_cards": cards,
        "health_card_counts": dict(sorted(card_counts.items())),
        "coverage_gaps": list(graph.get("coverage", {}).get("gaps", [])),
        "limitation": (
            "This is a bounded static and optional semantic assessment. Static "
            "evidence does not prove runtime selection or causality."
        ),
    }
