from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import threading

import pytest

from agent_doctor.analysis import AnalysisRequest, analyze
from agent_doctor.canonical import digest
from agent_doctor.human import build_human_summary
from agent_doctor.jsonschema_subset import validate as validate_json_schema
from agent_doctor.render import render_terminal
from agent_doctor.semantic_panel import (
    adjudicate_panel_answer,
    adjudicate_panel_answers,
    plan_semantic_questions,
)
from agent_doctor.semantic_workflow import (
    CodexCatalog,
    SemanticProviderRejected,
    SemanticWorkflowError,
    build_judge_prompt,
    build_provider_prompt,
    build_second_analyst_prompt,
    build_semantic_package,
    invoke_codex_provider,
    resolve_codex_selection,
    validate_manifest_digest,
    validate_provider_response,
)
from agent_doctor.semantic_workflow import _codex_failure_excerpt


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
) -> tuple[dict, dict, dict, dict]:
    answers: list[dict] = []
    peer_answers: list[dict] = []
    judgments: list[dict] = []
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
        peer_answer = json.loads(json.dumps(answer))
        peer_answer["answer_id"] = f"peer-answer-{index}"
        peer_answers.append(peer_answer)
        challenged = conflict and challenge_question_policy
        judgments.append(
            {
                "judgment_id": f"judgment-{index}",
                "question_id": question["question_id"],
                "analyst_a_answer_id": answer["answer_id"],
                "analyst_b_answer_id": peer_answer["answer_id"],
                "source_refs": question["source_refs"],
                "claim_refs": question["claim_refs"],
                "selected_label": None if challenged else label,
                "dimension": question["dimension"],
                "disposition": (
                    "challenged" if challenged else "corroborated_consensus"
                ),
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
                "recommendation_decision": {
                    "selected_from": (
                        "none"
                        if challenged or recommendation is None
                        else "analyst_a"
                    ),
                    "disposition": (
                        "not_applicable"
                        if challenged
                        else "accepted"
                        if recommendation is not None
                        else "not_applicable"
                    ),
                },
            }
        )
    analyst = {
        "schema_version": "agent-doctor-semantic-analyst-response/0.3",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "role": "analyst_a",
        "summary": "Bounded analyst A pass completed.",
        "answers": answers,
        "limitations": ["Static excerpts do not prove runtime selection."],
    }
    peer = {
        "schema_version": "agent-doctor-semantic-analyst-response/0.3",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "role": "analyst_b",
        "summary": "Bounded analyst B pass completed.",
        "answers": peer_answers,
        "limitations": ["No runtime behavior was observed."],
    }
    judge = {
        "schema_version": "agent-doctor-semantic-judge-response/0.4",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "summary": "Fresh-context judge pass completed.",
        "judgments": judgments,
        "limitations": ["No runtime behavior was observed."],
    }
    combined = {
        "schema_version": "agent-doctor-semantic-panel-response/0.4",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "analysts": {"analyst_a": analyst, "analyst_b": peer},
        "judge": judge,
    }
    return analyst, peer, judge, combined


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
            {
                "role": "analyst_a", "fresh_ephemeral_context": True,
                "source_order": "canonical", "execution_group": "parallel_analysts",
                "blind_to_peer": True,
                "response_digest": digest(response["analysts"]["analyst_a"]),
            },
            {
                "role": "analyst_b", "fresh_ephemeral_context": True,
                "source_order": "reversed", "execution_group": "parallel_analysts",
                "blind_to_peer": True,
                "response_digest": digest(response["analysts"]["analyst_b"]),
            },
            {
                "role": "judge", "fresh_ephemeral_context": True,
                "source_order": "canonical", "starts_after": ["analyst_a", "analyst_b"],
                "response_digest": digest(response["judge"]),
            },
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


def test_judge_schema_mechanically_binds_none_to_not_applicable(
    tmp_path: Path,
) -> None:
    _, _, package = _package(tmp_path)
    _, _, judge, _ = _panel_response(package["manifest"])
    schema = json.loads(
        Path("src/agent_doctor/data/schema/semantic-judgment.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert validate_json_schema(judge, schema) == []
    judge["judgments"][0]["recommendation_decision"] = {
        "selected_from": "none",
        "disposition": "accepted",
    }
    assert validate_json_schema(judge, schema)


def test_stale_prompt_contract_is_rejected_even_with_a_recomputed_digest(
    tmp_path: Path,
) -> None:
    _, _, package = _package(tmp_path)
    manifest = json.loads(json.dumps(package["manifest"]))
    manifest["prompt_contract_version"] = (
        "agent-doctor-semantic-panel-prompt/0.5"
    )
    manifest.pop("manifest_digest")
    manifest["manifest_digest"] = digest(manifest)
    assert "unsupported semantic prompt contract" in validate_manifest_digest(
        manifest
    )


def test_semantic_auto_scope_honors_exact_exclusion(tmp_path: Path) -> None:
    workspace, locations = _workspace(tmp_path)
    third = workspace / ".agents/skills/gamma/SKILL.md"
    third.parent.mkdir(parents=True)
    third.write_text(
        """---
name: gamma
description: Validate reviewed outputs without editing files.
---
# Gamma
Always validate reviewed outputs and never edit files.
""",
        encoding="utf-8",
    )
    graph = analyze(
        AnalysisRequest(workspace=workspace, project_trust="trusted")
    ).graph
    package = build_semantic_package(
        graph,
        source_selectors=(),
        exclude_source_selectors=(locations[1],),
        selection=_selection(),
        purpose="Exercise bounded automatic scope with an exact exclusion.",
    )
    manifest = package["manifest"]
    disclosed = {item["location"] for item in manifest["content_handles"]}
    assert locations[1] not in disclosed
    assert locations[0] in disclosed
    assert "workspace://.agents/skills/gamma/SKILL.md" in disclosed
    assert manifest["source_selection"]["selectors"] == []
    assert manifest["source_selection"]["exclude_selectors"] == [locations[1]]
    assert manifest["source_selection"]["selection_basis"] == (
        "bounded_discovered_non_inapplicable_skill_sources"
    )
    assert validate_manifest_digest(manifest) == []


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


def test_semantic_question_planner_prioritizes_relevant_pairs_without_deciding() -> None:
    handles = [
        {
            "source_ref": "source-spreadsheet-a",
            "handle_id": "handle-spreadsheet-a",
            "location": "workspace://skills/budget-spreadsheet/SKILL.md",
            "effective_scope": {"state": "applicable"},
            "claims": [
                {
                    "claim_ref": "claim-spreadsheet-a",
                    "dimension": "trigger",
                    "modality": "declarative",
                    "excerpt": "Create and validate budget spreadsheets with forecasts and formulas.",
                }
            ],
        },
        {
            "source_ref": "source-browser",
            "handle_id": "handle-browser",
            "location": "workspace://skills/browser/SKILL.md",
            "effective_scope": {"state": "applicable"},
            "claims": [
                {
                    "claim_ref": "claim-browser",
                    "dimension": "trigger",
                    "modality": "declarative",
                    "excerpt": "Navigate browser pages, click controls, and inspect visible state.",
                }
            ],
        },
        {
            "source_ref": "source-spreadsheet-b",
            "handle_id": "handle-spreadsheet-b",
            "location": "workspace://skills/forecast-workbook/SKILL.md",
            "effective_scope": {"state": "applicable"},
            "claims": [
                {
                    "claim_ref": "claim-spreadsheet-b",
                    "dimension": "trigger",
                    "modality": "declarative",
                    "excerpt": "Build budget spreadsheets containing formulas and forecast scenarios.",
                }
            ],
        },
    ]
    plan = plan_semantic_questions(handles, max_questions=1)
    question = plan["questions"][0]
    assert set(question["source_refs"]) == {
        "source-spreadsheet-a",
        "source-spreadsheet-b",
    }
    assert question["retrieval"]["score"] > 0
    assert question["retrieval"]["meaning"].startswith("retrieval priority only")


def test_semantic_content_agreement_stays_candidate_without_shared_region() -> None:
    answer = {
        "label": "semantic_conflict",
        "counterexample": {"status": "excluded"},
        "missing_evidence": [],
    }
    review = {
        "disposition": "corroborated",
        "label": "semantic_conflict",
        "counterexample": {"status": "excluded"},
        "missing_evidence": [],
    }
    decision = adjudicate_panel_answer(
        answer, review, shared_region_established=False
    )
    assert decision["state"] == "candidate"
    assert decision["severity"] is None
    assert decision["potential_severity"] == "high"
    assert decision["runtime_validation_needed"] is True


def test_judge_resolved_analyst_disagreement_is_never_a_finding_or_pass() -> None:
    answer_a = {
        "label": "semantic_conflict",
        "counterexample": {"status": "excluded"},
        "missing_evidence": [],
    }
    answer_b = {
        "label": "no_material_relation",
        "counterexample": {"status": "excluded"},
        "missing_evidence": [],
    }
    judgment = {
        "selected_label": "semantic_conflict",
        "disposition": "resolved_disagreement",
        "counterexample": {"status": "excluded"},
        "missing_evidence": [],
    }
    decision = adjudicate_panel_answers(answer_a, answer_b, judgment)
    assert decision["state"] == "candidate"
    assert decision["potential_severity"] == "high"
    assert decision["severity"] is None
    assert decision["resolved_disagreement"] is True
    assert decision["decisive"] is False


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
    assert len(manifest["semantic_panel"]["questions"]) == 16
    assert manifest["semantic_panel"]["coverage"]["question_limit"] == 16
    assert len(manifest["content_handles"]) == 32
    assert len(manifest["source_selection"]["question_limit_omitted_source_refs"]) == 38
    assert manifest["exclusions"]["counts"]["question_limit_omission"] == 38
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


def test_semantic_invoke_runs_two_blind_analysts_in_parallel_then_judge(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    manifest = package["manifest"]
    analyst_a, analyst_b, judge, _ = _panel_response(manifest)
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    calls: list[str] = []
    temporary_roots: set[str] = set()
    active_analysts = 0
    max_active_analysts = 0
    completed_analysts = 0

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal active_analysts, max_active_analysts, completed_analysts
        schema = Path(command[command.index("--output-schema") + 1]).name
        prompt = str(kwargs["input"])
        is_judge = schema == "semantic-judgment.schema.json"
        role = (
            "judge"
            if is_judge
            else "analyst_b"
            if prompt.startswith("You are analyst_b")
            else "analyst_a"
        )
        assert command[:4] == ["codex", "--ask-for-approval", "never", "exec"]
        with lock:
            calls.append(role)
            temporary_roots.add(command[command.index("--cd") + 1])
            if role != "judge":
                active_analysts += 1
                max_active_analysts = max(max_active_analysts, active_analysts)
            else:
                assert completed_analysts == 2
        if role != "judge":
            barrier.wait(timeout=5)
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(
            json.dumps(
                judge
                if role == "judge"
                else analyst_b
                if role == "analyst_b"
                else analyst_a
            ),
            encoding="utf-8",
        )
        if role != "judge":
            with lock:
                active_analysts -= 1
                completed_analysts += 1
        return subprocess.CompletedProcess(command, 0, stdout='{"type":"turn.completed"}\n', stderr="")

    payload = invoke_codex_provider(
        package,
        consent_digest=manifest["manifest_digest"],
        runner=runner,
    )
    assert set(calls[:2]) == {"analyst_a", "analyst_b"}
    assert calls[-1] == "judge"
    assert max_active_analysts == 2
    assert len(temporary_roots) == 3
    assert payload["invocation"]["ephemeral_session_count"] == 3
    assert [item["role"] for item in payload["invocation"]["calls"]] == [
        "analyst_a", "analyst_b", "judge"
    ]
    assert payload["response"]["judge"]["judgments"] == judge["judgments"]


def test_codex_failure_prefers_structured_error_over_stderr_warning() -> None:
    completed = subprocess.CompletedProcess(
        ["codex"],
        1,
        stdout=(
            '{"type":"turn.failed","error":{"message":"invalid_json_schema: '
            'uniqueItems is not permitted"}}\n'
        ),
        stderr="WARN state db discrepancy\n",
    )
    assert _codex_failure_excerpt(completed) == (
        "invalid_json_schema: uniqueItems is not permitted"
    )


def test_rejected_completed_panel_retains_three_safe_call_digests(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    analyst_a, analyst_b, judge, _ = _panel_response(package["manifest"])
    judge["judgments"][0]["claim_refs"] = ["claim-not-frozen"]

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        schema = Path(command[command.index("--output-schema") + 1]).name
        prompt = str(kwargs["input"])
        response = (
            judge
            if schema == "semantic-judgment.schema.json"
            else analyst_b
            if prompt.startswith("You are analyst_b")
            else analyst_a
        )
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps(response), encoding="utf-8")
        return subprocess.CompletedProcess(
            command, 0, stdout='{"type":"turn.completed"}\n', stderr=""
        )

    with pytest.raises(SemanticProviderRejected) as caught:
        invoke_codex_provider(
            package,
            consent_digest=package["manifest"]["manifest_digest"],
            runner=runner,
        )
    assert [item["role"] for item in caught.value.calls] == [
        "analyst_a",
        "analyst_b",
        "judge",
    ]
    assert all(item.get("response_digest") for item in caught.value.calls)
    assert caught.value.rejected_response_digest.startswith("sha256:")


def test_blind_analyst_and_judge_prompts_preserve_boundaries(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    analyst_a, analyst_b, _, _ = _panel_response(package["manifest"])
    analyst_prompt = build_provider_prompt(package)
    peer_prompt = build_second_analyst_prompt(package)
    judge_prompt = build_judge_prompt(package, analyst_a, analyst_b)
    alpha = "workspace://.agents/skills/alpha/SKILL.md"
    beta = "workspace://.agents/skills/beta/SKILL.md"
    assert analyst_prompt.index(alpha) < analyst_prompt.index(beta)
    assert peer_prompt.index(beta) < peer_prompt.index(alpha)
    assert "untrusted data" in analyst_prompt
    assert "blind independent analysts" in peer_prompt
    assert '"schema_version":"agent-doctor-analyst-answer-identity/0.1"' in analyst_prompt
    first_question = package["manifest"]["semantic_panel"]["questions"][0]
    assert first_question["question_id"] in analyst_prompt
    assert all(item in analyst_prompt for item in first_question["claim_refs"])
    assert '"claim_refs_allowed_only"' in analyst_prompt
    assert analyst_a["summary"] in judge_prompt
    assert analyst_b["summary"] in judge_prompt
    assert "untrusted data" in judge_prompt
    assert '"exact_join_constraints"' in judge_prompt
    assert '"recommendation_none_rule"' in judge_prompt
    assert analyst_a["answers"][0]["answer_id"] in judge_prompt
    assert analyst_b["answers"][0]["answer_id"] in judge_prompt


def test_manifest_minimization_prioritizes_late_routing_boundaries(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    alpha = workspace / ".agents/skills/alpha/SKILL.md"
    beta = workspace / ".agents/skills/beta/SKILL.md"
    alpha.parent.mkdir(parents=True)
    beta.parent.mkdir(parents=True)
    filler = "\n".join(f"General operating statement {index}." for index in range(20))
    alpha.write_text(
        "---\nname: alpha\ndescription: Handle all label workflows.\n---\n"
        + filler
        + "\nRoute direct subagent work without panels to `beta`.\n",
        encoding="utf-8",
    )
    beta.write_text(
        "---\nname: beta\ndescription: Handle direct subagent label workflows.\n---\n"
        "Use subagents without panel routing.\n",
        encoding="utf-8",
    )
    graph = analyze(
        AnalysisRequest(
            workspace=workspace,
            project_trust="trusted",
            semantic_mode="enabled",
        )
    ).graph
    package = build_semantic_package(
        graph,
        source_selectors=(
            "workspace://.agents/skills/alpha/SKILL.md",
            "workspace://.agents/skills/beta/SKILL.md",
        ),
        selection=_selection(),
        purpose="test",
    )
    alpha_handle = next(
        item
        for item in package["manifest"]["content_handles"]
        if item["location"].endswith("alpha/SKILL.md")
    )
    disclosed = "\n".join(item["excerpt"] for item in alpha_handle["claims"])
    assert "Route direct subagent work without panels" in disclosed
    assert package["manifest"]["schema_version"].endswith("/0.8")


def test_provider_cannot_set_product_severity(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    _, _, _, response = _panel_response(package["manifest"])
    response["analysts"]["analyst_a"]["answers"][0]["severity"] = "critical"
    errors = validate_provider_response(response, package["manifest"])
    assert any("forbidden authority field" in item for item in errors)


def test_judge_must_join_both_exact_answer_identities(tmp_path: Path) -> None:
    _, _, package = _package(tmp_path)
    _, _, _, response = _panel_response(package["manifest"])
    response["judge"]["judgments"][0]["analyst_b_answer_id"] = "wrong-peer"
    errors = validate_provider_response(response, package["manifest"])
    assert any("analyst_b_answer_id" in item for item in errors)


def test_corroborated_response_is_locally_adjudicated_and_manual_only(tmp_path: Path) -> None:
    workspace, _, package = _package(tmp_path)
    manifest = package["manifest"]
    _, _, _, response = _panel_response(manifest)
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
    terminal = render_terminal(graph)
    assert "Two blind semantic analysts and a fresh judge ran" in terminal
    assert "Semantic panel: codex-desktop/gpt-5.6-sol effort=max status=completed" in terminal
    assert f"manifest={manifest['manifest_digest']}" in terminal
    assert "Skills=2" in terminal
    assert "script_or_executable_body=1" in terminal
    assert "Agent Doctor cache=disabled" in terminal
    assert "Codex session=ephemeral_requested" in terminal
    assert "governed by the signed-in Codex account" in terminal
    assert "Model judge:" in terminal
    assert "Model analyst_a:" in terminal
    assert "Model analyst_b:" in terminal
    cards = {
        item["location"]: item
        for item in build_human_summary(graph)["health_cards"]
    }
    assert cards["workspace://.agents/skills/alpha/SKILL.md"][
        "semantic_evaluation"
    ] == "checked_with_candidates"


def test_judge_challenge_abstains_instead_of_forcing_a_finding(tmp_path: Path) -> None:
    workspace, _, package = _package(tmp_path)
    manifest = package["manifest"]
    _, _, _, response = _panel_response(manifest, challenge_question_policy=True)
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
    _, _, _, response = _panel_response(
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
