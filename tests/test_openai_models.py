from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from agent_doctor.canonical import content_digest
from agent_doctor.openai_models import (
    ModelSelectionRequest,
    check_official_model_profile,
    load_model_profile,
    parse_available_models,
    resolve_model,
    run_model_routing_suite,
    validate_model_profile,
    validate_model_routing_suite,
)


ROOT = Path("test-spec")
ROUTING_SUITE = ROOT / "scenarios/stage-06-model-routing-v0.1.json"
ROUTING_SCHEMA = ROOT / "schema/model-routing-suite.schema.json"


def test_bundled_model_profile_is_reviewed_and_attributable() -> None:
    profile = load_model_profile()
    assert not validate_model_profile(profile)
    assert profile["provider"] == "openai"
    assert profile["capabilities"]["codex.advisory_review"]["default_model"] == "gpt-5.6-sol"
    assert profile["capabilities"]["codex.advisory_review"]["default_reasoning_effort"] == "max"


def test_saved_models_response_proves_availability_not_ranking() -> None:
    available = parse_available_models(
        {
            "object": "list",
            "data": [
                {"id": "gpt-5.6-luna", "object": "model"},
                {"id": "gpt-5.6-sol", "object": "model"},
            ],
        }
    )
    decision = resolve_model(
        load_model_profile(),
        ModelSelectionRequest("codex.advisory_review", available_models=available),
        as_of=date(2026, 8, 17),
    )
    assert decision["selected_model"] == "gpt-5.6-sol"
    assert decision["availability"] == "available"
    assert decision["availability_proves_ranking"] is False


def test_product_semantics_requires_separate_qualification() -> None:
    profile = load_model_profile()
    request = ModelSelectionRequest(
        "semantic.reasoning_quality_first",
        available_models=frozenset({"gpt-5.6-sol"}),
        require_qualified=True,
    )
    blocked = resolve_model(profile, request, as_of=date(2026, 8, 17))
    assert blocked["qualification"] == "not_performed"
    assert blocked["invocation_ready"] is False
    assert blocked["blockers"] == ["model_not_qualified_for_product_semantics"]

    qualified = copy.deepcopy(profile)
    candidate = qualified["capabilities"]["semantic.reasoning_quality_first"]["candidates"][0]
    candidate["qualification"] = "qualified"
    candidate["qualification_ref"] = "qualification.synthetic-stage-04"
    qualified["qualifications"]["qualification.synthetic-stage-04"] = {
        "status": "qualified",
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "capability": "semantic.reasoning_quality_first",
        "adapter_version": "adapter-test/0.1",
        "prompt_contract_version": "prompt-test/0.1",
        "measurement_run_id": "synthetic-measurement-run",
        "reviewed_at": "2026-08-17",
    }
    ready = resolve_model(qualified, request, as_of=date(2026, 8, 17))
    assert ready["qualification"] == "qualified"
    assert ready["invocation_ready"] is True


def test_model_or_effort_change_invalidates_selection_digest() -> None:
    profile = load_model_profile()
    available = frozenset({"gpt-5.6-sol", "gpt-5.6-terra"})
    quality = resolve_model(
        profile,
        ModelSelectionRequest("semantic.reasoning_quality_first", available_models=available),
        as_of=date(2026, 8, 17),
    )
    lower_effort = resolve_model(
        profile,
        ModelSelectionRequest(
            "semantic.reasoning_quality_first",
            reasoning_effort="xhigh",
            available_models=available,
        ),
        as_of=date(2026, 8, 17),
    )
    balanced = resolve_model(
        profile,
        ModelSelectionRequest("semantic.reasoning_balanced", available_models=available),
        as_of=date(2026, 8, 17),
    )
    assert len({quality["selection_digest"], lower_effort["selection_digest"], balanced["selection_digest"]}) == 3


def test_stage_06_model_routing_suite_is_schema_valid_and_executable() -> None:
    suite = json.loads(ROUTING_SUITE.read_text(encoding="utf-8"))
    schema = json.loads(ROUTING_SCHEMA.read_text(encoding="utf-8"))
    assert not validate_model_routing_suite(suite, schema)
    report = run_model_routing_suite(suite, schema, load_model_profile())
    assert report["counts"] == {"passed": 11, "failed": 0, "invalid": 0}
    assert report["evidence_outcome"] == "valid"
    assert report["gate_outcome"] == "satisfied_for_executed_scenarios"
    assert report["measurement_status"] == "not_performed"


def _watched_profile() -> tuple[dict[str, object], dict[str, bytes]]:
    profile = copy.deepcopy(load_model_profile())
    bodies: dict[str, bytes] = {}
    for source in profile["provenance"]:
        watch = source["watch"]
        if watch["kind"] == "latest_model":
            body = f"---\nlatestModelInfo:\n  model: {watch['expected_model']}\n---\n".encode()
        elif watch["kind"] == "model_page":
            body = f"# Model\n\nModel ID: `{watch['expected_model_id']}`\n".encode()
        elif watch["kind"] == "model_catalog":
            body = "\n".join(f"- [model](/api/docs/models/{item}.md)" for item in watch["required_model_ids"]).encode()
        else:
            body = b"## List models\n\n**get** `/models`\n"
        source["content_digest"] = content_digest(body)
        bodies[source["uri"]] = body
    return profile, bodies


def test_official_source_check_detects_candidates_without_promotion() -> None:
    profile, bodies = _watched_profile()
    current = check_official_model_profile(profile, fetcher=lambda uri: bodies[uri])
    assert current["outcome"] == "current"
    assert current["automatic_promotion"] is False

    latest = next(item for item in profile["provenance"] if item["watch"]["kind"] == "latest_model")
    changed_bodies = dict(bodies)
    changed_bodies[latest["uri"]] = b"---\nlatestModelInfo:\n  model: gpt-future-sol\n---\n"
    candidate = check_official_model_profile(profile, fetcher=lambda uri: changed_bodies[uri])
    assert candidate["outcome"] == "candidate_change"
    assert candidate["latest_model_candidate"] == "gpt-future-sol"
    assert any(item["kind"] == "latest_model_changed" for item in candidate["changes"])
    assert candidate["automatic_promotion"] is False


def test_official_source_fetch_failure_is_execution_failure() -> None:
    profile, bodies = _watched_profile()
    first_uri = profile["provenance"][0]["uri"]

    def fetch(uri: str) -> bytes:
        if uri == first_uri:
            raise TimeoutError("synthetic timeout")
        return bodies[uri]

    report = check_official_model_profile(profile, fetcher=fetch)
    assert report["outcome"] == "execution_failed"
    assert report["errors"] == [{"source_id": profile["provenance"][0]["source_id"], "error": "TimeoutError"}]


def test_unofficial_profile_source_is_rejected() -> None:
    profile = copy.deepcopy(load_model_profile())
    profile["provenance"][0]["uri"] = "https://example.com/latest-model.md"
    assert any("allowlisted official OpenAI URI" in item for item in validate_model_profile(profile))


def test_qualification_cannot_be_asserted_without_an_attributable_record() -> None:
    profile = copy.deepcopy(load_model_profile())
    candidate = profile["capabilities"]["semantic.reasoning_quality_first"]["candidates"][0]
    candidate["qualification"] = "qualified"
    assert any("no attributable qualification record" in item for item in validate_model_profile(profile))


def test_codex_review_workflow_defaults_match_reviewed_profile() -> None:
    profile = load_model_profile()
    contract = profile["capabilities"]["codex.advisory_review"]
    workflow = Path(".github/workflows/codex-review.yml").read_text(encoding="utf-8")
    assert f"model: ${{{{ vars.CODEX_REVIEW_MODEL || '{contract['default_model']}' }}}}" in workflow
    assert f"effort: ${{{{ vars.CODEX_REVIEW_EFFORT || '{contract['default_reasoning_effort']}' }}}}" in workflow
