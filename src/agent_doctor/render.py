"""Read-only projections of the canonical sealed result graph."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .canonical import canonical_json
from .human import build_human_summary


STATIC_LIMITATION = "Static evidence does not assert runtime selection or causality."


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
        "",
        "What needs attention",
    ]
    if not summary["issues"]:
        lines.append("  Nothing was classified as a finding or candidate in completed checks.")
    for index, issue in enumerate(summary["issues"], start=1):
        impact = issue["impact"] or "not assigned"
        confidence = issue["confidence"] or "not assigned"
        lines.extend(
            [
                f"  {index}. [{issue['state']}] {issue['question']}",
                f"     Impact: {impact}; confidence: {confidence}",
                "     Where: " + (", ".join(issue["locations"]) or "no source location recorded"),
                f"     Why: {issue['why']}",
            ]
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
    for item in summary["unknowns"]:
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
                f"- Durable case: `{issue['case_id']}`",
            ]
        )
        for recommendation in issue["recommendations"]:
            lines.append(f"- Manual next step: {recommendation}")
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
