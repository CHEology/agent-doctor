"""Conservative human-facing views derived from a sealed result graph.

This module is a projection only.  It never changes case state, labels,
severity, confidence, applicability, or evidence provenance.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


ATTENTION_STATES = frozenset({"finding", "candidate"})
UNKNOWN_STATES = frozenset({"not_run", "insufficient_evidence"})
SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


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


def _evidence_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["evidence_id"]): item
        for item in graph.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }


def _claim_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["claim_id"]): item
        for item in graph.get("claims", [])
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    }


def _checks_by_source(
    graph: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    evidence = _evidence_map(graph)
    by_source: dict[str, list[dict[str, Any]]] = {}
    by_execution: dict[str, dict[str, Any]] = {}
    for check in graph.get("checks", []):
        if not isinstance(check, dict):
            continue
        execution_id = check.get("execution_id")
        if isinstance(execution_id, str):
            by_execution[execution_id] = check
        source_refs = {
            str(source_ref)
            for evidence_ref in check.get("evidence_refs", [])
            if evidence_ref in evidence
            for source_ref in evidence[evidence_ref].get("source_refs", [])
        }
        for source_ref in source_refs:
            by_source.setdefault(source_ref, []).append(check)
    return by_source, by_execution


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


def _issue_sort_key(item: Mapping[str, Any]) -> tuple[int, int, int, str]:
    return (
        SEVERITY_RANK.get(str(item.get("impact")), len(SEVERITY_RANK)),
        0 if item.get("state") == "finding" else 1,
        CONFIDENCE_RANK.get(str(item.get("confidence")), len(CONFIDENCE_RANK)),
        str(item.get("case_id", "")),
    )


def _claim_location(
    claim: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]
) -> str:
    source_ref = str(claim.get("source_ref", ""))
    location = str(sources.get(source_ref, {}).get("location", source_ref or "unknown"))
    span = claim.get("span", {})
    if isinstance(span, Mapping) and isinstance(span.get("start_line"), int):
        return f"{location}:{span['start_line']}"
    return location


def _case_excerpts(
    case: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
    claims: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return exact cited text without promoting a rationale into source text."""

    samples: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for claim_ref in case.get("claim_refs", []):
        claim = claims.get(str(claim_ref))
        if not claim or not isinstance(claim.get("excerpt"), str):
            continue
        excerpt = str(claim["excerpt"])
        location = _claim_location(claim, sources)
        identity = (location, excerpt)
        if identity in seen:
            continue
        seen.add(identity)
        samples.append(
            {
                "text": excerpt,
                "location": location,
                "provenance": "cited_claim",
                "reference": str(claim_ref),
            }
        )

    # Some deterministic cases (notably invalid-reference groups) cite parser
    # evidence directly instead of attaching the declarations as claim refs.
    if not samples:
        for evidence_ref in case.get("evidence_refs", []):
            record = evidence.get(str(evidence_ref))
            if (
                not record
                or record.get("kind") == "inferred"
                or not isinstance(record.get("excerpt"), str)
            ):
                continue
            excerpt = str(record["excerpt"])
            location = str(record.get("location") or "location not recorded")
            identity = (location, excerpt)
            if identity in seen:
                continue
            seen.add(identity)
            samples.append(
                {
                    "text": excerpt,
                    "location": location,
                    "provenance": str(record.get("kind", "unknown")),
                    "reference": str(evidence_ref),
                }
            )
    def location_key(item: Mapping[str, str]) -> tuple[str, int, str]:
        location, separator, tail = item["location"].rpartition(":")
        line = int(tail) if separator and tail.isdigit() else 2**31 - 1
        return (location if separator else item["location"], line, item["text"])

    return sorted(samples, key=location_key)


def _case_model_reviews(
    case: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, str]]:
    reviews: list[dict[str, str]] = []
    for evidence_ref in case.get("evidence_refs", []):
        record = evidence.get(str(evidence_ref))
        if not record or record.get("kind") != "inferred":
            continue
        provider = record.get("rule_or_provider", {})
        role = (
            str(provider.get("panel_role", "semantic_panel"))
            if isinstance(provider, Mapping)
            else "semantic_panel"
        )
        text = str(record.get("excerpt") or record.get("summary") or "")
        if not text:
            continue
        reviews.append(
            {
                "role": role,
                "text": text,
                "reference": str(evidence_ref),
            }
        )
    role_rank = {"judge": 0, "analyst_a": 1, "analyst_b": 2}
    return sorted(
        reviews,
        key=lambda item: (
            role_rank.get(item["role"], 3),
            item["role"],
            item["reference"],
        ),
    )


def _judgment_basis(
    case: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]]
) -> str:
    inferred = any(
        evidence.get(str(reference), {}).get("kind") == "inferred"
        for reference in case.get("evidence_refs", [])
    )
    if case.get("state") == "candidate":
        return "model_candidate_unconfirmed" if inferred else "candidate_unconfirmed"
    if inferred:
        return "model_inferred_locally_adjudicated"
    return "deterministic_rule_finding"


def _semantic_calls(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    reproducibility = graph.get("reproducibility", {})
    if not isinstance(reproducibility, Mapping):
        return []
    calls = reproducibility.get("semantic_calls", [])
    if not isinstance(calls, list):
        return []
    return [item for item in calls if isinstance(item, dict)]


def _semantic_not_applicable(graph: Mapping[str, Any]) -> bool:
    return any(
        isinstance(item, Mapping)
        and item.get("family") == "semantic"
        and isinstance(item.get("reason"), Mapping)
        and item["reason"].get("code")
        == "semantic_relationship_scope_not_applicable"
        for item in graph.get("checks", [])
    )


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
    checks_by_source, checks_by_execution = _checks_by_source(graph)
    evidence = _evidence_map(graph)
    semantic_mode = str(
        graph.get("run", {}).get("modes", {}).get("semantic", "unavailable")
    )
    semantic_not_applicable = _semantic_not_applicable(graph)
    completed_semantic_calls = [
        item
        for item in _semantic_calls(graph)
        if item.get("status") == "completed"
        and item.get("response_validation") == "valid"
    ]
    semantic_selected_refs = {
        str(source_ref)
        for call in completed_semantic_calls
        for source_ref in call.get("source_selection", {}).get(
            "selected_source_refs", []
        )
    }
    cards: list[dict[str, Any]] = []
    for source_ref, source in sorted(
        sources.items(), key=lambda item: str(item[1].get("location", ""))
    ):
        if source.get("type") != "skill_body":
            continue
        related = [item for item in cases if source_ref in item.get("source_refs", [])]
        content_related = [
            item
            for item in related
            if checks_by_execution.get(str(item.get("check_ref")), {}).get("family")
            != "applicability"
        ]
        # A provider-wide semantic execution error describes an unfinished
        # analysis dimension, not a defect in every selected Skill. Preserve
        # it in the case counts and semantic dimension while keeping the
        # whole-Skill status tied to completed evidence.
        health_deciding_cases = [
            item
            for item in content_related
            if not (
                checks_by_execution.get(str(item.get("check_ref")), {}).get("family")
                == "semantic"
                and item.get("state") in UNKNOWN_STATES | {"error"}
            )
        ]
        applicability_cases = [
            item
            for item in related
            if checks_by_execution.get(str(item.get("check_ref")), {}).get("family")
            == "applicability"
        ]
        states = Counter(str(item.get("state")) for item in content_related)
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
        elif any(item.get("state") == "error" for item in health_deciding_cases):
            status = "error"
            explanation = "At least one attempted check failed to execute."
        elif any(item.get("state") == "finding" for item in health_deciding_cases):
            status = "attention"
            explanation = "At least one checked interaction is a finding."
        elif any(item.get("state") == "candidate" for item in health_deciding_cases):
            status = "review_candidate"
            explanation = "At least one checked interaction needs bounded validation."
        elif any(item.get("state") in UNKNOWN_STATES for item in health_deciding_cases):
            status = "unknown"
            explanation = "At least one content-health check was not completed decisively."
        elif source.get("effective_scope", {}).get("state") == "inapplicable":
            status = "not_applicable"
            explanation = "The Skill is inventoried but not applicable in this frozen scope."
        else:
            status = "no_issue_in_checked_scope"
            explanation = (
                "No issue was emitted by completed content-health checks; runtime "
                "selection and unfinished semantic work are reported separately."
            )
        source_claims = [item for item in claims if item.get("source_ref") == source_ref]
        reference_claims = [
            item for item in source_claims if item.get("kind") == "reference"
        ]
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
        semantic_related = [
            item
            for item in related
            if checks_by_execution.get(str(item.get("check_ref")), {}).get("family")
            == "semantic"
        ]
        stale_cases = [
            item for item in related if "stale_reference" in _labels(item)
        ]
        maintenance_checks = [
            item
            for item in checks_by_source.get(source_ref, [])
            if item.get("family") == "maintenance"
        ]
        if stale_cases:
            maintenance = "attention"
            maintenance_reason = "An explicit incompatibility proves a stale reference."
        elif any(item.get("state") == "error" for item in maintenance_checks):
            maintenance = "error"
            maintenance_reason = "A declared freshness contract could not be evaluated."
        elif any(item.get("state") == "pass" for item in maintenance_checks):
            maintenance = "checked_no_issue"
            maintenance_reason = "An explicit version contract was checked and matched."
        elif any(
            item.get("state") == "insufficient_evidence"
            for item in maintenance_checks
        ):
            maintenance = "insufficient_evidence"
            maintenance_reason = "Declared version facts did not decide compatibility."
        elif reference_claims:
            maintenance = "insufficient_evidence"
            maintenance_reason = (
                "References exist, but no authoritative freshness or compatibility "
                "contract was established; file age was not used."
            )
        else:
            maintenance = "not_applicable"
            maintenance_reason = (
                "No reference freshness contract was present in the parsed Skill claims."
            )
        if semantic_not_applicable:
            semantic = "not_applicable"
        elif completed_semantic_calls and source_ref not in semantic_selected_refs:
            semantic = "not_selected"
        elif semantic_related:
            if any(item.get("state") == "error" for item in semantic_related):
                semantic = "error"
            elif any(item.get("state") == "not_run" for item in semantic_cases):
                semantic = "pending_provider_run"
            elif any(
                item.get("state") in {"finding", "candidate"}
                for item in semantic_cases
            ):
                semantic = "checked_with_candidates"
            elif any(
                item.get("state") == "insufficient_evidence"
                for item in semantic_cases
            ):
                semantic = "insufficient_evidence"
            else:
                semantic = "checked"
        elif semantic_mode == "disabled":
            semantic = "disabled"
        elif semantic_mode == "enabled":
            semantic = "pending_provider_run"
        else:
            semantic = "unavailable"
        runtime_observed = any(
            item.get("kind") == "runtime" and source_ref in item.get("source_refs", [])
            for item in evidence.values()
        )
        runtime_selection = (
            "observed"
            if runtime_observed
            else "unobserved"
            if applicability_cases
            else "not_assessed"
        )
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
                semantic
            ),
            "maintenance_freshness": maintenance,
            "static_applicability": str(
                source.get("effective_scope", {}).get("state", "unknown")
            ),
            "runtime_selection": runtime_selection,
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
                "semantic_evaluation": semantic,
                "maintenance_evaluation": maintenance,
                "maintenance_reason": maintenance_reason,
                "runtime_selection": runtime_selection,
            }
        )
    return cards


def build_human_summary(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return an answer-first, lossless summary linked to durable graph IDs."""

    semantic_mode = str(
        graph.get("run", {}).get("modes", {}).get("semantic", "unavailable")
    )
    sources = _source_map(graph)
    actions = _action_map(graph)
    claims = _claim_map(graph)
    evidence = _evidence_map(graph)
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
            "judgment_basis": _judgment_basis(case, evidence),
            "source_excerpts": _case_excerpts(
                case, sources=sources, claims=claims, evidence=evidence
            ),
            "model_reviews": _case_model_reviews(case, evidence),
        }
        if case.get("state") in ATTENTION_STATES:
            issues.append(item)
        elif case.get("state") in UNKNOWN_STATES or case.get("state") == "error":
            unknowns.append(item)

    issues.sort(key=_issue_sort_key)

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

    semantic_calls = _semantic_calls(graph)
    semantic_completed = any(
        item.get("status") == "completed"
        and item.get("response_validation") == "valid"
        for item in semantic_calls
    )
    semantic_not_applicable = _semantic_not_applicable(graph)
    if semantic_completed:
        limitation = (
            "This is a bounded local assessment. Two blind semantic analysts and "
            "a fresh judge ran; their outputs remain inferred evidence under local "
            "adjudication. Static evidence does not prove runtime selection or causality."
        )
    elif semantic_not_applicable:
        limitation = (
            "Cross-Skill semantic relationship analysis was not applicable because "
            "fewer than two Skills were selected; no provider call started. Static "
            "evidence does not prove runtime selection or causality."
        )
    elif semantic_mode == "disabled":
        limitation = (
            "This deterministic-only assessment did not run semantic analysis. "
            "Static evidence does not prove runtime selection or causality."
        )
    else:
        limitation = (
            "This is a bounded local assessment. Semantic coverage is enabled, but "
            "this result does not contain a completed provider panel; use semantic run "
            "for the full bounded review. Static evidence does not prove runtime "
            "selection or causality."
        )

    return {
        "verdict": verdict,
        "issues": issues,
        "unknowns": unknowns,
        "health_cards": cards,
        "health_card_counts": dict(sorted(card_counts.items())),
        "coverage_gaps": list(graph.get("coverage", {}).get("gaps", [])),
        "limitation": limitation,
    }
