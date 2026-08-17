"""Read-only projections of the canonical sealed result graph."""

from __future__ import annotations

import json
from collections import Counter
import re
from typing import Any

from .canonical import canonical_json
from .human import build_human_summary


STATIC_LIMITATION = "Static evidence does not assert runtime selection or causality."
TERMINAL_TOP_ISSUES = 3
TERMINAL_LOW_ISSUES = 2
TERMINAL_EXCERPTS_PER_ISSUE = 3
TERMINAL_MODEL_REVIEWS_PER_ISSUE = 3
TERMINAL_RISK_LEADS = 3
TERMINAL_NON_ISSUE_LEADS = 2


JUDGMENT_BASIS_TEXT = {
    "deterministic_rule_finding": "deterministic rule finding",
    "model_inferred_locally_adjudicated": (
        "model-inferred finding retained by local adjudication; not runtime proof"
    ),
    "candidate_unconfirmed": "candidate only; not established",
    "model_candidate_unconfirmed": (
        "model-inferred candidate only; not established"
    ),
}


def _compact_text(value: Any, *, limit: int = 260) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _issue_examples(
    issues: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, dict[str, Any]]], int]:
    ranked = list(enumerate(issues, start=1))
    highest = ranked[:TERMINAL_TOP_ISSUES]
    selected_ids = {str(item["case_id"]) for _, item in highest}
    lower: list[tuple[int, dict[str, Any]]] = []
    if len(ranked) > TERMINAL_TOP_ISSUES:
        for rank, item in reversed(ranked):
            if str(item["case_id"]) in selected_ids:
                continue
            lower.append((rank, item))
            selected_ids.add(str(item["case_id"]))
            if len(lower) == TERMINAL_LOW_ISSUES:
                break
        lower.reverse()
    omitted = len(issues) - len(selected_ids)
    return highest, lower, omitted


def _append_terminal_issue(
    lines: list[str], rank: int, issue: dict[str, Any]
) -> None:
    impact = issue["impact"] or "not assigned"
    confidence = issue["confidence"] or "not assigned"
    basis = JUDGMENT_BASIS_TEXT.get(
        str(issue.get("judgment_basis")), str(issue.get("judgment_basis", "unknown"))
    )
    lines.extend(
        [
            f"  {rank}. [{issue['state']}] {issue['question']}",
            f"     Impact: {impact}; confidence: {confidence}",
            f"     Basis: {basis}",
            "     Where: "
            + (", ".join(issue["locations"]) or "no source location recorded"),
            f"     Why: {issue['why']}",
        ]
    )
    excerpts = issue.get("source_excerpts", [])
    for sample in excerpts[:TERMINAL_EXCERPTS_PER_ISSUE]:
        lines.append(
            f"     Trigger [{sample['location']}]: {_compact_text(sample['text'])}"
        )
    if len(excerpts) > TERMINAL_EXCERPTS_PER_ISSUE:
        lines.append(
            f"     Trigger: … {len(excerpts) - TERMINAL_EXCERPTS_PER_ISSUE} "
            "additional cited excerpt(s) remain in Markdown/JSON."
        )
    for review in issue.get("model_reviews", [])[:TERMINAL_MODEL_REVIEWS_PER_ISSUE]:
        lines.append(
            f"     Model {review['role']}: {_compact_text(review['text'])} "
            f"({review['reference']})"
        )
    if len(issue.get("model_reviews", [])) > TERMINAL_MODEL_REVIEWS_PER_ISSUE:
        lines.append(
            "     Model review: … "
            f"{len(issue['model_reviews']) - TERMINAL_MODEL_REVIEWS_PER_ISSUE} additional "
            "panel rationale(s) remain in Markdown/JSON."
        )
    counterexample = issue.get("counterexample")
    if isinstance(counterexample, dict):
        status = "excluded" if counterexample.get("excluded") else "still open"
        lines.append(
            f"     Counterexample ({status}): "
            + _compact_text(counterexample.get("considered", "none recorded"))
        )
    recommendations = issue["recommendations"] or [
        "Inspect the cited evidence manually; no automatic repair is authorized."
    ]
    for recommendation in recommendations[:3]:
        lines.append(f"     Next: {recommendation}")
    if len(recommendations) > 3:
        lines.append(
            f"     Next: … {len(recommendations) - 3} additional bounded action(s) "
            "are retained in the sealed result."
        )
    lines.append(f"     Reference: {issue['case_id']}")


def _lead_excerpts(lead: dict[str, Any]) -> list[dict[str, str]]:
    """Rank exact excerpts for display without changing diagnostic meaning."""

    rationale = " ".join(
        str(review.get("text", "")) for review in lead.get("model_reviews", [])
    ).casefold()
    terms = {
        token
        for token in re.findall(r"[\w-]+", rationale)
        if len(token) >= 4
    }

    def key(sample: dict[str, str]) -> tuple[int, str, str]:
        excerpt = sample.get("text", "").casefold()
        overlap = sum(term in excerpt for term in terms)
        return (-overlap, sample.get("location", ""), sample.get("text", ""))

    return sorted(lead.get("source_excerpts", []), key=key)


def _review_identity(review: dict[str, str]) -> str:
    details = [review.get("label", "unknown")]
    if review.get("disposition"):
        details.append(review["disposition"])
    return f"{review.get('role', 'unknown')} [{'; '.join(details)}]"


def _append_terminal_semantic_lead(
    lines: list[str], rank: int, lead: dict[str, Any]
) -> None:
    lines.extend(
        [
            f"  {rank}. [unconfirmed] {lead['question']}",
            "     Local status: insufficient evidence; this is not a finding or candidate.",
            "     Where: "
            + (", ".join(lead["locations"]) or "no source location recorded"),
        ]
    )
    excerpts = _lead_excerpts(lead)
    for sample in excerpts[:TERMINAL_EXCERPTS_PER_ISSUE]:
        lines.append(
            f"     Cited [{sample['location']}]: {_compact_text(sample['text'])}"
        )
    if len(excerpts) > TERMINAL_EXCERPTS_PER_ISSUE:
        lines.append(
            f"     Cited: … {len(excerpts) - TERMINAL_EXCERPTS_PER_ISSUE} "
            "additional exact excerpt(s) remain in Markdown/JSON."
        )
    for review in lead.get("model_reviews", [])[:TERMINAL_MODEL_REVIEWS_PER_ISSUE]:
        lines.append(
            f"     Model {_review_identity(review)}: "
            f"{_compact_text(review.get('text', ''))} ({review['reference']})"
        )
    counterexample = lead.get("counterexample")
    if isinstance(counterexample, dict):
        status = "excluded" if counterexample.get("excluded") else "still open"
        lines.append(
            f"     Local counterexample ({status}): "
            + _compact_text(counterexample.get("considered", "none recorded"))
        )
    lines.append(f"     Reference: {lead['case_id']}")


def render_json(graph: dict[str, Any], *, pretty: bool = True) -> str:
    if pretty:
        return json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return canonical_json(graph) + "\n"


def _labels(case: dict[str, Any]) -> list[str]:
    return [item["label"] for item in case.get("assessments", [])]


def _qualifiers(case: dict[str, Any]) -> list[str]:
    return [item["kind"] for item in case.get("validation_qualifiers", [])]


def render_debug_terminal(graph: dict[str, Any]) -> str:
    run = graph["run"]
    cases = graph.get("interaction_cases", [])
    source_counts = Counter(item["status"] for item in graph.get("inventory", {}).get("sources", []))
    state_counts = Counter(item["state"] for item in cases)
    lines = [
        f"Agent Doctor {run['product_version']} — {run['outcome']}",
        f"result {graph['result_id']} | sealed={str(graph.get('sealed', False)).lower()} | scope {graph['scope']['scope_id']}",
        f"inventory: {sum(source_counts.values())} source(s) "
        + " ".join(f"{key}={value}" for key, value in sorted(source_counts.items())),
        f"cases: {len(cases)} " + " ".join(f"{key}={value}" for key, value in sorted(state_counts.items())),
        STATIC_LIMITATION,
    ]
    for case in cases:
        labels = ",".join(_labels(case)) or "none"
        qualifiers = ",".join(_qualifiers(case)) or "none"
        impact = case.get("severity") or case.get("potential_severity") or "none"
        confidence = case.get("confidence") or "none"
        lines.append(
            f"[{case['state']}] {case['case_id']} check={case['check_ref']} "
            f"labels={labels} qualifiers={qualifiers} severity={impact} confidence={confidence}"
        )
        lines.append(f"  {case['question']}")
        if case.get("source_refs"):
            lines.append("  sources: " + ", ".join(case["source_refs"]))
        if case.get("evidence_refs"):
            lines.append("  evidence: " + ", ".join(case["evidence_refs"]))
    if graph.get("finding_groups"):
        lines.append("finding groups:")
        for group in graph["finding_groups"]:
            lines.append(
                f"  {group['group_id']} kind={group['relationship_kind']} members="
                + ",".join(group["member_case_refs"])
            )
    gaps = graph.get("coverage", {}).get("gaps", [])
    if gaps:
        lines.append(f"coverage gaps ({len(gaps)}):")
        for gap in gaps:
            lines.append(f"  {gap['state']} {gap['check_ref']}: {gap['reason'].get('code', 'unspecified')}")
    if graph.get("next_actions"):
        lines.append("next actions:")
        for action in graph["next_actions"]:
            lines.append(f"  {action['action_id']} [{action['kind']}] {action['summary']}")
    return "\n".join(lines) + "\n"


def render_terminal(graph: dict[str, Any]) -> str:
    """Render an answer-first terminal report with durable IDs as references."""

    run = graph["run"]
    summary = build_human_summary(graph)
    inventory_count = len(graph.get("inventory", {}).get("sources", []))
    skill_count = len(summary["health_cards"])
    lines = [
        f"Agent Doctor {run['product_version']}",
        summary["verdict"],
        (
            f"Scope: {', '.join(graph['scope']['selected_regions'])} | "
            f"inventoried {inventory_count} source(s), including {skill_count} Skill(s)"
        ),
        summary["limitation"],
    ]
    semantic_calls = [
        item
        for item in graph.get("reproducibility", {}).get("semantic_calls", [])
        if isinstance(item, dict)
    ]
    if semantic_calls:
        call = semantic_calls[-1]
        disclosure = call.get("disclosure_summary", {})
        coverage = call.get("question_coverage", {})
        exclusions = disclosure.get("exclusion_counts", {})
        retention = disclosure.get("retention_and_cache", {})
        excluded_total = sum(
            value for value in exclusions.values() if isinstance(value, int)
        )
        exclusion_detail = ", ".join(
            f"{key}={value}" for key, value in sorted(exclusions.items())
        ) or "none recorded"
        lines.extend(
            [
                (
                    "Semantic panel: "
                    f"{call.get('provider', 'unknown')}/{call.get('model', 'unknown')} "
                    f"effort={call.get('reasoning_effort', 'unknown')} "
                    f"status={call.get('status', 'unknown')}"
                ),
                (
                    "Semantic disclosure: "
                    f"manifest={call.get('consent_manifest_digest', 'unknown')} | "
                    f"Skills={disclosure.get('content_handle_count', 0)}, "
                    f"claims={disclosure.get('disclosed_claim_count', 0)}, "
                    f"questions={coverage.get('emitted_question_count', 0)}/"
                    f"{coverage.get('eligible_question_count', 0)}, "
                    f"excluded={excluded_total}"
                ),
                (
                    "Semantic exclusions: " + exclusion_detail
                ),
                (
                    "Semantic retention: "
                    f"Agent Doctor cache={retention.get('agent_doctor_semantic_cache', 'unknown')}; "
                    f"Codex session={retention.get('codex_session', 'unknown')}; "
                    f"provider={retention.get('provider_retention', 'not recorded')}"
                ),
                (
                    "Semantic artifacts: "
                    f"{call.get('artifact_dir', 'not recorded')}"
                ),
            ]
        )
    lines.extend(["", "What needs attention"])
    if not summary["issues"]:
        lines.append("  Nothing was classified as a finding or candidate in completed checks.")
    highest, lower, omitted_issues = _issue_examples(summary["issues"])
    if highest:
        lines.append("  Highest-priority review items:")
        for rank, issue in highest:
            _append_terminal_issue(lines, rank, issue)
    if lower:
        lines.append("  Lower-priority examples:")
        for rank, issue in lower:
            _append_terminal_issue(lines, rank, issue)
    if omitted_issues:
        lines.append(
            f"  … {omitted_issues} additional finding/candidate(s) remain in the "
            "sealed result and complete Markdown/JSON projections."
        )

    semantic_leads = summary["semantic_review_leads"]
    risk_leads = semantic_leads["risk"]
    non_issue_leads = semantic_leads["non_issue"]
    if risk_leads or non_issue_leads:
        lines.extend(
            [
                "",
                "Unconfirmed semantic review leads",
                "  These are bounded model hypotheses retained for human review; local "
                "adjudication did not promote them to findings or candidates.",
            ]
        )
    if risk_leads:
        lines.append("  Most risk-like hypotheses:")
        for rank, lead in enumerate(risk_leads[:TERMINAL_RISK_LEADS], start=1):
            _append_terminal_semantic_lead(lines, rank, lead)
        omitted = len(risk_leads) - TERMINAL_RISK_LEADS
        if omitted > 0:
            lines.append(
                f"  … {omitted} additional risk-like semantic lead(s) remain in "
                "Markdown/JSON."
            )
    if non_issue_leads:
        lines.append("  Clearest no-material-relation or complementarity examples:")
        for rank, lead in enumerate(
            non_issue_leads[:TERMINAL_NON_ISSUE_LEADS], start=1
        ):
            _append_terminal_semantic_lead(lines, rank, lead)
        omitted = len(non_issue_leads) - TERMINAL_NON_ISSUE_LEADS
        if omitted > 0:
            lines.append(
                f"  … {omitted} additional low-risk semantic example(s) remain in "
                "Markdown/JSON."
            )

    lines.extend(["", "Skill health (bounded to completed checks)"])
    if not summary["health_cards"]:
        lines.append("  No discovered Skill body was available for a health card.")
    else:
        lines.append(
            "  Summary: "
            + ", ".join(
                f"{key}={value}"
                for key, value in summary["health_card_counts"].items()
            )
        )
    priority_cards = [
        card
        for card in summary["health_cards"]
        if card["status"] in {"attention", "review_candidate", "error"}
    ]
    gap_cards = [
        card for card in summary["health_cards"] if card["status"] == "unknown"
    ][:6]
    display_cards = priority_cards + gap_cards
    if not display_cards:
        display_cards = summary["health_cards"][:6]
    for card in display_cards:
        lines.append(f"  [{card['status']}] {card['location']}")
        lines.append(f"     {card['explanation']}")
        if card["labels"]:
            lines.append("     Relationships: " + ", ".join(card["labels"]))
        lines.append(
            "     Semantic: "
            + card["semantic_evaluation"]
            + "; maintenance: "
            + card["maintenance_evaluation"]
        )
        lines.append(
            "     Runtime selection: "
            + card["runtime_selection"]
            + "; maintenance basis: "
            + card["maintenance_reason"]
        )
        lines.append(
            "     Coverage: "
            + ", ".join(
                f"{key.replace('_', ' ')}={value}"
                for key, value in card["health_dimensions"].items()
            )
        )
    omitted_cards = len(summary["health_cards"]) - len(display_cards)
    if omitted_cards > 0:
        lines.append(
            f"  … {omitted_cards} additional Skill card(s) are summarized above; "
            "use Markdown or JSON for the complete list."
        )

    lines.extend(["", "Still unknown or not completed"])
    if not summary["unknowns"] and not summary["coverage_gaps"]:
        lines.append("  No additional gap was recorded.")
    semantic_lead_ids = {
        item["case_id"]
        for group in summary["semantic_review_leads"].values()
        for item in group
    }
    for item in summary["unknowns"]:
        if item["case_id"] in semantic_lead_ids:
            continue
        lines.append(
            f"  [{item['state']}] {item['question']} (reference {item['case_id']})"
        )
    known_unknown_ids = {item["check_ref"] for item in summary["unknowns"]}
    for gap in summary["coverage_gaps"]:
        if gap.get("check_ref") not in known_unknown_ids:
            lines.append(
                f"  [{gap.get('state')}] {gap.get('check_ref')}: "
                f"{gap.get('reason', {}).get('code', 'unspecified')}"
            )

    lines.extend(["", "Technical reference"])
    lines.append(
        f"  result {graph['result_id']} | sealed={str(graph.get('sealed', False)).lower()} "
        f"| outcome={run['outcome']} | scope={graph['scope']['scope_id']}"
    )
    for case in graph.get("interaction_cases", []):
        lines.append(
            f"  {case['case_id']} [{case['state']}] check={case['check_ref']} "
            f"evidence_records={len(case.get('evidence_refs', []))}"
        )
    for group in graph.get("finding_groups", []):
        lines.append(
            f"  {group['group_id']} members=" + ",".join(group["member_case_refs"])
        )
    return "\n".join(lines) + "\n"


def render_markdown(graph: dict[str, Any]) -> str:
    run = graph["run"]
    summary = build_human_summary(graph)
    lines = [
        "# Agent Doctor report",
        "",
        f"**Verdict:** {summary['verdict']}",
        "",
        summary["limitation"],
        "",
        "## What needs attention",
        "",
    ]
    if not summary["issues"]:
        lines.append("No finding or candidate was emitted by the completed checks.")
    for issue in summary["issues"]:
        locations = ", ".join(f"`{item}`" for item in issue["locations"]) or "none recorded"
        labels = ", ".join(f"`{item}`" for item in issue["labels"]) or "none"
        lines.extend(
            [
                f"### {issue['question']}",
                "",
                f"- State/impact/confidence: `{issue['state']}` / `{issue['impact']}` / `{issue['confidence']}`",
                f"- Relationship labels: {labels}",
                f"- Locations: {locations}",
                f"- Why: {issue['why']}",
                "- Judgment basis: "
                + JUDGMENT_BASIS_TEXT.get(
                    str(issue.get("judgment_basis")),
                    str(issue.get("judgment_basis", "unknown")),
                ),
                f"- Durable case: `{issue['case_id']}`",
            ]
        )
        excerpts = issue.get("source_excerpts", [])
        if excerpts:
            lines.append(f"- Cited source excerpts ({len(excerpts)}):")
            for sample in excerpts:
                lines.append(
                    f"  - `{sample['location']}` — {_compact_text(sample['text'], limit=600)} "
                    f"(`{sample['reference']}`)"
                )
        reviews = issue.get("model_reviews", [])
        if reviews:
            lines.append(f"- Model-panel rationales ({len(reviews)}; inferred evidence):")
            for review in reviews:
                lines.append(
                    f"  - **{review['role']}** — {_compact_text(review['text'], limit=600)} "
                    f"(`{review['reference']}`)"
                )
        counterexample = issue.get("counterexample")
        if isinstance(counterexample, dict):
            status = "excluded" if counterexample.get("excluded") else "still open"
            lines.append(
                f"- Counterexample ({status}): "
                + _compact_text(counterexample.get("considered", "none recorded"), limit=600)
            )
        for recommendation in issue["recommendations"]:
            lines.append(f"- Manual next step: {recommendation}")
        lines.append("")

    semantic_leads = summary["semantic_review_leads"]
    all_semantic_leads = semantic_leads["risk"] + semantic_leads["non_issue"]
    lines.extend(["## Unconfirmed semantic review leads", ""])
    if not all_semantic_leads:
        lines.append("No unconfirmed model-panel relationship lead was retained.")
    else:
        lines.append(
            "These are inferred model hypotheses retained for review. Every item below "
            "remains `insufficient_evidence`; none is a finding or candidate."
        )
        lines.append("")
    for lead in all_semantic_leads:
        locations = ", ".join(f"`{item}`" for item in lead["locations"]) or "none recorded"
        lines.extend(
            [
                f"### {lead['question']}",
                "",
                f"- Lead class: `{lead['lead_kind']}`; local state: `insufficient_evidence`.",
                f"- Locations: {locations}",
                f"- Durable case: `{lead['case_id']}`",
            ]
        )
        excerpts = _lead_excerpts(lead)
        if excerpts:
            lines.append(f"- Exact cited source excerpts ({len(excerpts)}):")
            for sample in excerpts:
                lines.append(
                    f"  - `{sample['location']}` — {_compact_text(sample['text'], limit=600)} "
                    f"(`{sample['reference']}`)"
                )
        lines.append(
            f"- Model-panel rationales ({len(lead['model_reviews'])}; inferred evidence):"
        )
        for review in lead["model_reviews"]:
            lines.append(
                f"  - **{_review_identity(review)}** — "
                f"{_compact_text(review['text'], limit=600)} (`{review['reference']}`)"
            )
        counterexample = lead.get("counterexample")
        if isinstance(counterexample, dict):
            status = "excluded" if counterexample.get("excluded") else "still open"
            lines.append(
                f"- Local counterexample ({status}): "
                + _compact_text(counterexample.get("considered", "none recorded"), limit=600)
            )
        lines.append("")

    lines.extend(["## Skill health", ""])
    if not summary["health_cards"]:
        lines.append("No discovered Skill body was available for a health card.")
    for card in summary["health_cards"]:
        dimension_text = ", ".join(
            f"{key.replace('_', ' ')}=`{value}`"
            for key, value in card["health_dimensions"].items()
        )
        lines.extend(
            [
                f"- **`{card['location']}` — `{card['status']}`.** {card['explanation']} "
                f"Coverage: {dimension_text}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Technical detail",
            "",
        f"Result `{graph['result_id']}` is **{run['outcome']}** and `sealed={str(graph.get('sealed', False)).lower()}`.",
        "",
        STATIC_LIMITATION,
        "",
        "## Run and scope",
        "",
        f"- Run: `{run['run_id']}`",
        f"- Scope: `{graph['scope']['scope_id']}` ({', '.join(graph['scope']['selected_regions'])})",
        f"- Product/result: `{run['product_version']}` / `{graph['schema_version']}`",
        f"- Taxonomy/rules/normalization/grouping: `{run['taxonomy_version']}` / `{run['rule_set_version']}` / `{run['normalization_version']}` / `{run['grouping_version']}`",
        f"- Semantic contract: `{run['semantic_contract_version']}`; mode `{run['modes']['semantic']}`",
        f"- Platform profiles: {', '.join(f'`{item}`' for item in run['platform_profiles'])}",
        "",
        "## Coverage",
        "",
        "| Family | Attempted | Completed | Not run | Error | Abstained |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in graph.get("coverage", {}).get("by_family", []):
        lines.append(
            f"| {row['family']} | {row['attempted']} | {row['completed']} | {row['not_run']} | {row['error']} | {row['abstained']} |"
        )
    if graph.get("coverage", {}).get("gaps"):
        lines.extend(["", "Coverage gaps:", ""])
        for gap in graph["coverage"]["gaps"]:
            lines.append(f"- `{gap['check_ref']}` — `{gap['state']}`: `{gap['reason'].get('code', 'unspecified')}`")

    lines.extend(["", "## Inventory", "", "| Source ID | Type | Status | Location | Revision |", "| --- | --- | --- | --- | --- |"])
    for source in graph.get("inventory", {}).get("sources", []):
        lines.append(
            f"| `{source['source_id']}` | {source['type']} | {source['status']} | `{source['location']}` | `{source.get('revision') or 'none'}` |"
        )

    lines.extend(["", "## Interaction cases", ""])
    if not graph.get("interaction_cases"):
        lines.append("No material interaction case was emitted.")
    for case in graph.get("interaction_cases", []):
        lines.extend(
            [
                f"### `{case['case_id']}` — {case['state']}",
                "",
                case["question"],
                "",
                f"- Check: `{case['check_ref']}`",
                f"- Dimension/region: `{case['dimension_ref']}` / `{case['region_ref']}`",
                f"- Labels: {', '.join(f'`{item}`' for item in _labels(case)) or 'none'}",
                f"- Qualifiers: {', '.join(f'`{item}`' for item in _qualifiers(case)) or 'none'}",
                f"- Severity/potential/confidence: `{case.get('severity')}` / `{case.get('potential_severity')}` / `{case.get('confidence')}`",
                f"- Sources: {', '.join(f'`{item}`' for item in case.get('source_refs', [])) or 'none'}",
                f"- Claims: {', '.join(f'`{item}`' for item in case.get('claim_refs', [])) or 'none'}",
                f"- Evidence: {', '.join(f'`{item}`' for item in case.get('evidence_refs', [])) or 'none'}",
                f"- Counterexample: {case.get('counterexample', {})}",
                "",
            ]
        )

    lines.extend(["## Finding groups", ""])
    if not graph.get("finding_groups"):
        lines.append("No finding groups.")
    for group in graph.get("finding_groups", []):
        lines.append(
            f"- `{group['group_id']}` ({group['relationship_kind']}): "
            f"members {', '.join(f'`{item}`' for item in group['member_case_refs'])}. {group['relationship_summary']}"
        )

    lines.extend(["", "## Evidence lineage", ""])
    for evidence in graph.get("evidence", []):
        parent_text = ", ".join(f"`{item}`" for item in evidence.get("parent_evidence_refs", [])) or "none"
        excerpt = evidence.get("excerpt")
        suffix = f" Excerpt: `{excerpt}`" if excerpt else ""
        lines.append(
            f"- `{evidence['evidence_id']}` **{evidence['kind']}**, producer `{evidence['producer']}`, parents {parent_text}: {evidence['summary']}.{suffix}"
        )

    lines.extend(["", "## Next actions", ""])
    if not graph.get("next_actions"):
        lines.append("No next action proposed.")
    for action in graph.get("next_actions", []):
        lines.append(f"- `{action['action_id']}` **{action['kind']}**: {action['summary']} Bounds: `{action['bounds']}`")
    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
            f"- Input revision manifest: `{graph['reproducibility']['input_revision_manifest']}`",
            f"- Configuration digest: `{graph['reproducibility']['configuration_digest']}`",
            f"- Canonicalization: `{graph['reproducibility']['canonicalization']}`",
            "",
        ]
    )
    return "\n".join(lines)


def semantic_projection(graph: dict[str, Any]) -> dict[str, Any]:
    """Canonical fields that every renderer/CI projection must preserve."""

    return {
        "result_id": graph.get("result_id"),
        "sealed": graph.get("sealed"),
        "run_outcome": graph.get("run", {}).get("outcome"),
        "cases": [
            {
                "case_id": case["case_id"],
                "check_ref": case["check_ref"],
                "state": case["state"],
                "labels": _labels(case),
                "qualifiers": _qualifiers(case),
                "severity": case.get("severity"),
                "potential_severity": case.get("potential_severity"),
                "confidence": case.get("confidence"),
                "evidence_refs": case.get("evidence_refs", []),
            }
            for case in graph.get("interaction_cases", [])
        ],
        "groups": [
            {"group_id": group["group_id"], "members": group["member_case_refs"]}
            for group in graph.get("finding_groups", [])
        ],
        "coverage": graph.get("coverage"),
    }
