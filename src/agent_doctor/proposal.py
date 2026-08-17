"""Non-executable, authority-free manual proposals from sealed findings."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .canonical import digest, stable_id
from .jsonschema_subset import SchemaError, validate
from .schema import validate_result


class ProposalError(ValueError):
    pass


def load_manual_proposal_schema() -> dict[str, Any]:
    resource = files("agent_doctor").joinpath("data/schema/manual-proposal.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_manual_proposal(proposal: dict[str, Any]) -> list[SchemaError]:
    errors = validate(proposal, load_manual_proposal_schema())
    if proposal.get("executable_operations"):
        errors.append(SchemaError("$.executable_operations", "manual-only proposals must contain zero executable operations"))
    identity = {key: value for key, value in proposal.items() if key not in {"proposal_id", "proposal_digest"}}
    expected_digest = digest(identity)
    if proposal.get("proposal_digest") != expected_digest:
        errors.append(SchemaError("$.proposal_digest", "does not match canonical proposal content"))
    with_digest = dict(identity)
    with_digest["proposal_digest"] = expected_digest
    if proposal.get("proposal_id") != stable_id("proposal", with_digest):
        errors.append(SchemaError("$.proposal_id", "does not match canonical proposal identity"))
    return sorted(errors, key=lambda item: (item.path, item.message))


def build_manual_proposal(graph: dict[str, Any], selected_case_refs: list[str]) -> dict[str, Any]:
    result_errors = validate_result(graph, require_sealed=True)
    if result_errors:
        raise ProposalError("manual proposals require a valid sealed result")
    selected = sorted(set(selected_case_refs))
    if not selected:
        raise ProposalError("select at least one finding or candidate case")
    cases = {item["case_id"]: item for item in graph["interaction_cases"]}
    unknown = [item for item in selected if item not in cases]
    if unknown:
        raise ProposalError(f"unknown case reference(s): {', '.join(unknown)}")
    invalid_states = [item for item in selected if cases[item]["state"] not in {"finding", "candidate"}]
    if invalid_states:
        raise ProposalError(f"only findings and candidates can be proposed: {', '.join(invalid_states)}")
    action_by_id = {item["action_id"]: item for item in graph["next_actions"]}
    action_refs = sorted(
        {
            action_ref
            for case_ref in selected
            for action_ref in cases[case_ref].get("next_action_refs", [])
            if action_ref in action_by_id
        }
    )
    if not action_refs:
        raise ProposalError("selected cases contain no bounded manual action")
    source_refs = sorted({source_ref for case_ref in selected for source_ref in cases[case_ref]["source_refs"]})
    source_by_id = {item["source_id"]: item for item in graph["inventory"]["sources"]}
    base: dict[str, Any] = {
        "schema_version": "agent-doctor-manual-proposal/0.1",
        "result_ref": graph["result_id"],
        "selected_case_refs": selected,
        "mode": "manual_only",
        "authority": "none",
        "executable_operations": [],
        "manual_actions": [
            {
                "action_ref": action_ref,
                "kind": action_by_id[action_ref]["kind"],
                "summary": action_by_id[action_ref]["summary"],
                "bounds": action_by_id[action_ref]["bounds"],
            }
            for action_ref in action_refs
        ],
        "created_from_revisions": [
            {
                "source_ref": source_ref,
                "location": source_by_id[source_ref]["location"],
                "revision": source_by_id[source_ref].get("revision"),
            }
            for source_ref in source_refs
            if source_ref in source_by_id
        ],
        "preview": [
            "No executable filesystem operation is present or authorized.",
            *[f"MANUAL: {action_by_id[action_ref]['summary']}" for action_ref in action_refs],
        ],
        "risks": [
            "Manual edits can diverge from this snapshot; inspect current content before acting.",
            "This artifact grants no authority and provides no automatic prior-state protection.",
        ],
        "verification_plan": [
            "After any separately authorized manual edit, rerun Agent Doctor over the same selected scope.",
            "Compare the new sealed result and source revisions with this proposal's result and revision references.",
        ],
        "rollback_plan": {
            "supported": False,
            "reason": "Agent Doctor did not apply an operation or capture protected prior state; rollback remains manual.",
        },
    }
    base["proposal_digest"] = digest(base)
    base["proposal_id"] = stable_id("proposal", base)
    errors = validate_manual_proposal(base)
    if errors:
        raise ProposalError("manual proposal invariant failure: " + "; ".join(str(item) for item in errors))
    return base
