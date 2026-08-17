from __future__ import annotations

import copy
import json
from pathlib import Path

from agent_doctor.canonical import canonical_json
from agent_doctor.ci import CIPolicy, evaluate_ci, exit_code
from agent_doctor.golden import execute
from agent_doctor.human import build_human_summary
from agent_doctor.render import (
    render_debug_terminal,
    render_json,
    render_markdown,
    render_terminal,
)


def _golden(case_id: str) -> dict:
    suite = json.loads(Path("test-spec/fixtures/golden-v0.1.json").read_text(encoding="utf-8"))
    case = next(item for item in suite["cases"] if item["id"] == case_id)
    return execute(case)["graph"]


def test_all_renderers_project_without_mutating_or_losing_ids() -> None:
    graph = _golden("G-001")
    before = canonical_json(graph)
    terminal = render_terminal(graph)
    markdown = render_markdown(graph)
    json_graph = json.loads(render_json(graph))
    assert canonical_json(graph) == before
    assert json_graph == graph
    assert "What needs attention" in terminal
    assert "Skill health" in terminal
    assert "Technical detail" in markdown
    for case in graph["interaction_cases"]:
        assert case["case_id"] in terminal
        assert case["case_id"] in markdown
    for group in graph["finding_groups"]:
        assert group["group_id"] in terminal
        assert group["group_id"] in markdown
        assert all(member in terminal and member in markdown for member in group["member_case_refs"])


def test_human_projection_is_conservative_and_debug_projection_remains_available() -> None:
    graph = _golden("G-003")
    summary = build_human_summary(graph)
    assert summary["issues"][0]["state"] == "candidate"
    assert "scope_overlap" in summary["issues"][0]["labels"]
    assert "semantic_relationships" in summary["health_cards"][0]["health_dimensions"]
    assert summary["health_cards"][0]["health_dimensions"]["maintenance_freshness"] == "not_applicable"
    assert "runtime_selection" in summary["health_cards"][0]["health_dimensions"]
    assert "runtime" in summary["limitation"].lower()
    debug = render_debug_terminal(graph)
    assert "cases:" in debug
    assert graph["interaction_cases"][0]["case_id"] in debug


def test_human_report_shows_cited_sentences_and_model_provenance() -> None:
    graph = _golden("G-001")
    summary = build_human_summary(graph)
    issue = summary["issues"][0]
    assert issue["judgment_basis"] == "model_inferred_locally_adjudicated"
    assert [item["location"] for item in issue["source_excerpts"]] == [
        "repo/AGENTS.md:12",
        "repo/skills/fast-update/SKILL.md:31",
    ]
    assert issue["model_reviews"]

    terminal = render_terminal(graph)
    markdown = render_markdown(graph)
    assert "Trigger [repo/AGENTS.md:12]" in terminal
    assert "Model semantic_panel:" in terminal
    assert "Counterexample (excluded)" in terminal
    assert "Cited source excerpts (2)" in markdown
    assert "inferred evidence" in markdown


def test_terminal_selects_severity_extremes_and_counts_omitted_cases() -> None:
    graph = _golden("G-001")
    template = graph["interaction_cases"][0]
    severities = ["low", "critical", "medium", "high", "info", "medium"]
    cases = []
    for index, severity in enumerate(severities):
        case = copy.deepcopy(template)
        case["case_id"] = f"case-render-{index}"
        case["question"] = f"Rendered {severity} issue {index}?"
        case["severity"] = severity
        cases.append(case)
    graph["interaction_cases"] = cases
    graph["finding_groups"] = []

    terminal = render_terminal(graph)
    assert "1. [finding] Rendered critical issue 1?" in terminal
    assert "2. [finding] Rendered high issue 3?" in terminal
    assert "3. [finding] Rendered medium issue 2?" in terminal
    assert "Lower-priority examples:" in terminal
    assert "5. [finding] Rendered low issue 0?" in terminal
    assert "6. [finding] Rendered info issue 4?" in terminal
    assert "… 1 additional finding/candidate(s) remain" in terminal


def test_ci_distinguishes_policy_and_execution_failure() -> None:
    graph = _golden("G-001")
    policy = CIPolicy(fail_at_or_above="high", required_families=("inventory", "adjudication"))
    decision = evaluate_ci(graph, policy)
    assert decision["outcome"] == "policy_failed"
    assert exit_code(decision) == 2
    assert len(graph["interaction_cases"]) == decision["durable_case_count"]

    unsealed = copy.deepcopy(graph)
    unsealed["sealed"] = False
    failed = evaluate_ci(unsealed, policy)
    assert failed["outcome"] == "execution_failed"
    assert exit_code(failed) == 3


def test_ci_required_disabled_family_is_execution_failure() -> None:
    graph = _golden("G-015")
    decision = evaluate_ci(graph, CIPolicy(required_families=("semantic",)))
    assert decision["outcome"] == "execution_failed"
