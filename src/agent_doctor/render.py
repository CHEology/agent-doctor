"""Read-only projections of the canonical sealed result graph."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .canonical import canonical_json


STATIC_LIMITATION = "Static evidence does not assert runtime selection or causality."


def render_json(graph: dict[str, Any], *, pretty: bool = True) -> str:
    if pretty:
        return json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return canonical_json(graph) + "\n"


def _labels(case: dict[str, Any]) -> list[str]:
    return [item["label"] for item in case.get("assessments", [])]


def _qualifiers(case: dict[str, Any]) -> list[str]:
    return [item["kind"] for item in case.get("validation_qualifiers", [])]


def render_terminal(graph: dict[str, Any]) -> str:
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


def render_markdown(graph: dict[str, Any]) -> str:
    run = graph["run"]
    lines = [
        "# Agent Doctor report",
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
