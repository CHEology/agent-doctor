from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent_doctor.golden import execute
from agent_doctor.proposal import ProposalError, build_manual_proposal, validate_manual_proposal


def _result(case_id: str) -> dict:
    suite = json.loads(Path("test-spec/fixtures/golden-v0.1.json").read_text(encoding="utf-8"))
    case = next(item for item in suite["cases"] if item["id"] == case_id)
    return execute(case)["graph"]


def test_manual_proposal_has_no_authority_or_operations() -> None:
    graph = _result("G-004")
    case_ref = graph["interaction_cases"][0]["case_id"]
    proposal = build_manual_proposal(graph, [case_ref])
    assert not validate_manual_proposal(proposal)
    assert proposal["mode"] == "manual_only"
    assert proposal["authority"] == "none"
    assert proposal["executable_operations"] == []
    assert proposal["rollback_plan"]["supported"] is False
    assert proposal["created_from_revisions"]


def test_manual_proposal_rejects_tampering_and_nonfinding() -> None:
    graph = _result("G-004")
    case_ref = graph["interaction_cases"][0]["case_id"]
    proposal = build_manual_proposal(graph, [case_ref])
    tampered = copy.deepcopy(proposal)
    tampered["executable_operations"] = [{"operation": "delete"}]
    assert any(item.path == "$.executable_operations" for item in validate_manual_proposal(tampered))

    pass_graph = _result("G-002")
    pass_ref = pass_graph["interaction_cases"][0]["case_id"]
    with pytest.raises(ProposalError):
        build_manual_proposal(pass_graph, [pass_ref])
