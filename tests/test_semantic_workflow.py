from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess

import pytest

from agent_doctor.analysis import AnalysisRequest, analyze
from agent_doctor.canonical import digest
from agent_doctor.semantic_panel import plan_semantic_questions
from agent_doctor.semantic_workflow import (
    CodexCatalog,
    SemanticWorkflowError,
    build_critic_prompt,
    build_provider_prompt,
    build_semantic_package,
    invoke_codex_provider,
    resolve_codex_selection,
    validate_manifest_digest,
    validate_provider_response,
)


def _workspace(tmp_path: Path) -> tuple[Path, tuple[str, str]]:
    workspace = tmp_path / "repo"
    first = workspace / ".agents/skills/alpha/SKILL.md"
    second = workspace / ".agents/skills/beta/SKILL.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(
        """---
name: alpha
description: Review changes and always ask before editing.
---
# Alpha
Always ask before editing a file.
""",
        encoding="utf-8",
    )
    second.write_text(
        """---
name: beta
description: Review changes and edit directly without questions.
---
# Beta
Never ask a question before editing a file.
""",
        encoding="utf-8",
    )
    (first.parent / "scripts").mkdir()
    (first.parent / "scripts/check.sh").write_text(
        "echo should-not-be-disclosed\n", encoding="utf-8"
    )
    return workspace, (
        "workspace://.agents/skills/alpha/SKILL.md",
        "workspace://.agents/skills/beta/SKILL.md",
    )


def _selection() -> dict:
    catalog = CodexCatalog(
        models=frozenset({"gpt-5.6-sol"}),
        efforts={
            "gpt-5.6-sol": frozenset(
                {"low", "medium", "high", "xhigh", "max"}
            )
        },
        snapshot_digest=digest(["gpt-5.6-sol"]),
    )
    return resolve_codex_selection(observed_on=date(2026, 8, 17), catalog=catalog)


def _package(tmp_path: Path) -> tuple[Path, tuple[str, str], dict]:
    workspace, locations = _workspace(tmp_path)
    graph = analyze(
        AnalysisRequest(
            workspace=workspace,
            project_trust="trusted",
            semantic_mode="enabled",
        )
    ).graph
    package = build_semantic_package(
        graph,
        source_selectors=locations,
        selection=_selection(),
        purpose="Compare the two synthetic Skill behaviors.",
    )
    return workspace, locations, package


def _panel_response(
    manifest: dict,
    *,
    challenge_question_policy: bool = False,
    open_question_policy: bool = False,
    recommendation_kind: str = "clarify_trigger",
) -> tuple[dict, dict, dict]:
    answers: list[dict] = []
    reviews: list[dict] = []
    for index, question in enumerate(manifest["semantic_panel"]["questions"]):
        conflict = question["dimension"] == "question_policy"
        label = "semantic_conflict" if conflict else "no_material_relation"
        recommendation = (
            {
                "kind": recommendation_kind,
                "summary": "Clarify the two Skill boundaries manually.",
                "expected_benefit": "Reduce contradictory question handling.",
                "risk": "An overly narrow trigger may hide a useful Skill.",
                "verification": "Rerun the frozen scenario and review both citations.",
            }
            if conflict
            else None
        )
        answer = {
            "answer_id": f"answer-{index}",
            "question_id": question["question_id"],
            "source_refs": question["source_refs"],
            "claim_refs": question["claim_refs"],
            "label": label,
            "dimension": question["dimension"],
            "rationale": (
                "One Skill requires a question while the other forbids it."
                if conflict
                else "The trigger descriptions alone do not establish a material relation."
            ),
            "citations": question["handle_refs"],
            "shared_region": {
                "status": "supported",
                "explanation": "Both static Skill scopes apply to the workspace.",
            },
            "distinct_contributions": ["The two instructions express different behavior."],
            "counterexample": {
                "status": "open" if conflict and open_question_policy else "excluded",
                "explanation": "The scopes may be disjoint." if open_question_policy else "Both address change review.",
            },
            "missing_evidence": [],
            "recommendation": recommendation,
        }
        answers.append(answer)
        challenged = conflict and challenge_question_policy
        reviews.append(
            {
                "review_id": f"review-{index}",
                "question_id": question["question_id"],
                "answer_id": answer["answer_id"],
                "source_refs": question["source_refs"],
                "claim_refs": question["claim_refs"],
                "label": "no_material_relation" if challenged else label,
                "dimension": question["dimension"],
                "disposition": "challenged" if challenged else "corroborated",
                "rationale": (
                    "The excerpts may govern different tasks."
                    if challenged
                    else "The label survives a reversed-order review."
                ),
                "citations": question["handle_refs"],
                "counterexample": {
                    "status": "open" if challenged else "excluded",
                    "explanation": "Task boundaries remain unclear." if challenged else "No disjoint trigger is stated.",
                },
                "missing_evidence": [],
                "recommendation_disposition": (
                    "challenged"
                    if challenged and recommendation is not None
                    else "accepted"
                    if recommendation is not None
                    else "not_applicable"
                ),
            }
        )
    analyst = {
        "schema_version": "agent-doctor-semantic-analyst-response/0.2",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "summary": "Bounded analyst pass completed.",
        "answers": answers,
        "limitations": ["Static excerpts do not prove runtime selection."],
    }
    critic = {
        "schema_version": "agent-doctor-semantic-critic-response/0.2",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "summary": "Independent reversed-order critic pass completed.",
        "reviews": reviews,
        "limitations": ["No runtime behavior was observed."],
    }
    combined = {
        "schema_version": "agent-doctor-semantic-panel-response/0.2",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "analyst": analyst,
        "critic": critic,
    }
    return analyst, critic, combined


def _invocation(manifest: dict, response: dict) -> dict:
    return {
        "status": "completed",
        "provider": manifest["provider"],
        "model": manifest["model"],
        "reasoning_effort": manifest["reasoning_effort"],
        "consent_manifest_digest": manifest["manifest_digest"],
        "selection_digest": manifest["selection"]["selection_digest"],
        "response_digest": digest(response),
        "tool_activity_observed": [],
        "calls": [
            {"role": "analyst", "fresh_ephemeral_context": True, "source_order": "canonical"},
            {"role": "critic", "fresh_ephemeral_context": True, "source_order": "reversed"},
        ],
        "release_qualified": False,
    }


def test_semantic_manifest_is_minimized_bounded_and_excludes_scripts(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    manifest = package["manifest"]
    assert manifest["model"] == "gpt-5.6-sol"
    assert manifest["reasoning_effort"] == "max"
    assert len(manifest["content_handles"]) == 2
    assert manifest["exclusions"]["counts"]["script_or_executable_body"] == 1
    assert "should-not-be-disclosed" not in repr(manifest)
    assert manifest["semantic_panel"]["coverage"]["complete"] is True
    assert manifest["semantic_panel"]["calls"][1]["source_order"] == "reversed"
    assert manifest["qualification"]["release_qualified"] is False


def test_semantic_question_planner_is_stable_and_discloses_omissions() -> None:
    handles = [
        {
            "source_ref": f"source-{index:016x}",
            "handle_id": f"handle-{index:016x}",
            "effective_scope": {"state": "applicable"},
            "claims": [{"claim_ref": f"claim-{index:016x}", "dimension": "trigger"}],
        }
        for index in range(3)
    ]
    first = plan_semantic_questions(handles, max_questions=2)
    second = plan_semantic_questions(list(reversed(handles)), max_questions=2)
    assert first == second
    assert first["coverage"] == {
        "eligible_pair_count": 3,
        "planned_pair_count": 2,
        "eligible_question_count": 3,
        "emitted_question_count": 2,
        "omitted_question_count": 1,
        "complete": False,
        "question_limit": 2,
        "omission_reason": "bounded_semantic_question_limit",
    }


def test_large_semantic_scope_discloses_only_handles_used_by_bounded_questions() -> None:
    sources = []
    claims = []
    for index in range(70):
        source_ref = f"source-{index:024x}"
        sources.append(
            {
                "source_id": source_ref,
                "type": "skill_body",
                "status": "discovered",
                "location": f"workspace://skills/{index}/SKILL.md",
                "revision": "sha256:" + f"{index:064x}",
                "effective_scope": {"state": "applicable"},
                "sensitivity": [],
            }
        )
        claims.append(
            {
                "claim_id": f"claim-{index:024x}",
                "source_ref": source_ref,
                "kind": "trigger",
                "dimension": "trigger",
                "modality": "declarative",
                "qualifiers": [],
                "excerpt": f"Use Skill {index} for its bounded task.",
                "span": {"start_line": 1},
            }
        )
    graph = {
        "run": {"modes": {"semantic": "enabled"}},
        "inventory": {"sources": sources},
        "claims": claims,
        "reproducibility": {"input_revision_manifest": "sha256:" + "f" * 64},
    }
    package = build_semantic_package(
        graph,
        source_selectors=(),
        selection=_selection(),
        purpose="Bounded large-scope fixture.",
    )
    manifest = package["manifest"]
    assert len(manifest["semantic_panel"]["questions"]) == 32
    assert len(manifest["content_handles"]) == 64
    assert len(manifest["source_selection"]["question_limit_omitted_source_refs"]) == 6
    assert manifest["exclusions"]["counts"]["question_limit_omission"] == 6
    assert validate_manifest_digest(manifest) == []


def test_semantic_invoke_requires_exact_digest_before_any_runner_call(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    called = False

    def runner(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("runner must not start")

    with pytest.raises(SemanticWorkflowError, match="consent digest"):
        invoke_codex_provider(
            package,
            consent_digest="sha256:" + "0" * 64,
            runner=runner,  # type: ignore[arg-type]
        )
    assert called is False


def test_semantic_invoke_runs_two_fresh_schema_valid_tool_free_turns(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    manifest = package["manifest"]
    analyst, critic, _ = _panel_response(manifest)
    calls: list[str] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        schema = Path(command[command.index("--output-schema") + 1]).name
        calls.append(schema)
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(
            json.dumps(critic if schema == "semantic-critique.schema.json" else analyst),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout='{"type":"turn.completed"}\n', stderr="")

    payload = invoke_codex_provider(
        package,
        consent_digest=manifest["manifest_digest"],
        runner=runner,
    )
    assert calls == ["semantic-response.schema.json", "semantic-critique.schema.json"]
    assert payload["invocation"]["ephemeral_session_count"] == 2
    assert payload["invocation"]["calls"][1]["source_order"] == "reversed"
    assert payload["response"]["critic"]["reviews"] == critic["reviews"]


def test_critic_prompt_reverses_source_order_and_quotes_input_as_data(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    analyst, _, _ = _panel_response(package["manifest"])
    analyst_prompt = build_provider_prompt(package)
    critic_prompt = build_critic_prompt(package, analyst)
    alpha = "workspace://.agents/skills/alpha/SKILL.md"
    beta = "workspace://.agents/skills/beta/SKILL.md"
    assert analyst_prompt.index(alpha) < analyst_prompt.index(beta)
    assert critic_prompt.index(beta) < critic_prompt.index(alpha)
    assert "untrusted data" in analyst_prompt
    assert "Attempt to refute" in critic_prompt


def test_provider_cannot_set_product_severity(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    _, _, response = _panel_response(package["manifest"])
    response["analyst"]["answers"][0]["severity"] = "critical"
    errors = validate_provider_response(response, package["manifest"])
    assert any("forbidden authority field" in item for item in errors)


def test_corroborated_response_is_locally_adjudicated_and_manual_only(tmp_path: Path) -> None:
    workspace, _, package = _package(tmp_path)
    manifest = package["manifest"]
    _, _, response = _panel_response(manifest)
    graph = analyze(
        AnalysisRequest(
            workspace=workspace,
            project_trust="trusted",
            semantic_mode="enabled",
            semantic_manifest=manifest,
            semantic_invocation=_invocation(manifest, response),
            semantic_response=response,
            semantic_consent_digest=manifest["manifest_digest"],
        )
    ).graph
    semantic_case = next(
        item
        for item in graph["interaction_cases"]
        if item["dimension_ref"] == "question_policy"
        and item["question"].startswith("What material semantic relationship")
    )
    assert graph["sealed"] is True
    assert semantic_case["state"] == "finding"
    assert semantic_case["severity"] == "high"
    action = next(
        item for item in graph["next_actions"] if item["action_id"] in semantic_case["next_action_refs"]
    )
    assert action["authority"] == "none"
    assert action["bounds"]["automatic_apply"] is False
    assert action["bounds"]["proposal_kind"] == "clarify_trigger"
    evidence = {item["evidence_id"]: item for item in graph["evidence"]}
    assert all(evidence[reference]["kind"] == "inferred" for reference in semantic_case["evidence_refs"])


def test_critic_disagreement_abstains_instead_of_forcing_a_finding(tmp_path: Path) -> None:
    workspace, _, package = _package(tmp_path)
    manifest = package["manifest"]
    _, _, response = _panel_response(manifest, challenge_question_policy=True)
    graph = analyze(
        AnalysisRequest(
            workspace=workspace,
            project_trust="trusted",
            semantic_mode="enabled",
            semantic_manifest=manifest,
            semantic_invocation=_invocation(manifest, response),
            semantic_response=response,
            semantic_consent_digest=manifest["manifest_digest"],
        )
    ).graph
    semantic_case = next(
        item
        for item in graph["interaction_cases"]
        if item["dimension_ref"] == "question_policy"
        and item["question"].startswith("What material semantic relationship")
    )
    assert semantic_case["state"] == "insufficient_evidence"
    assert semantic_case["assessments"] == []
    check = next(
        item for item in graph["checks"] if item["execution_id"] == semantic_case["check_ref"]
    )
    assert check["completeness"] == "partial"


def test_incompatible_model_recommendation_is_not_promoted(tmp_path: Path) -> None:
    workspace, _, package = _package(tmp_path)
    manifest = package["manifest"]
    _, _, response = _panel_response(
        manifest, recommendation_kind="add_negative_trigger"
    )
    graph = analyze(
        AnalysisRequest(
            workspace=workspace,
            project_trust="trusted",
            semantic_mode="enabled",
            semantic_manifest=manifest,
            semantic_invocation=_invocation(manifest, response),
            semantic_response=response,
            semantic_consent_digest=manifest["manifest_digest"],
        )
    ).graph
    semantic_case = next(
        item
        for item in graph["interaction_cases"]
        if item["dimension_ref"] == "question_policy"
        and item["question"].startswith("What material semantic relationship")
    )
    actions = {
        item["action_id"]: item for item in graph["next_actions"]
    }
    selected_actions = [actions[item] for item in semantic_case["next_action_refs"]]
    assert all(
        item.get("bounds", {}).get("proposal_kind") != "add_negative_trigger"
        for item in selected_actions
    )
    assert all(item["authority"] == "none" for item in selected_actions)
