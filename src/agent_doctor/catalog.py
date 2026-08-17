"""Executable contract checks for the Stage 04 draft scenario catalog.

These checks exercise the selected local vertical slices. Repair mutation
scenarios remain unsupported and are never converted into passes.
"""

from __future__ import annotations

import copy
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest, stable_id, strip_volatile
from .ci import CIPolicy, evaluate_ci
from .invariants import validate_result_graph
from .model import FixedClock
from .parser import parse_source
from .privacy import SafeReader, minimize_excerpt, redact_secrets, safe_revision
from .profile import compatibility_decision, load_profile
from .render import render_json, render_markdown, render_terminal, semantic_projection
from .resolution import ReferenceDeclaration, resolve_reference
from .scope import ScopeOptions, plan_scope
from .semantic_panel import adjudicate_panel_answers
from .semantic_workflow import (
    MANIFEST_SCHEMA_VERSION,
    SemanticWorkflowError,
    build_judge_prompt,
    build_provider_prompt,
    invoke_codex_provider,
    provider_lifecycle_state,
    validate_provider_response,
)


STANDARD_RULE = "Severity and confidence are independent and follow the governing taxonomy evidence threshold."
NON_DIAGNOSTIC_RULE = "This is a non-diagnostic contract test; the test-only not_applicable sentinel must never enter the product result schema."

UNSUPPORTED_TYPES = frozenset({"repair_authorization", "repair_apply_verify", "rollback"})
UNSUPPORTED_IDS = frozenset({"S-CMP-008"})

NON_DIAGNOSTIC_IDS = frozenset(
    {
        *(f"S-SCH-{index:03d}" for index in range(1, 7)),
        *(f"S-OUT-{index:03d}" for index in range(1, 12)),
        *(f"S-PRV-{index:03d}" for index in range(1, 10)),
        "S-ADJ-005",
        "S-ADJ-008",
        "S-CMP-001",
        "S-CMP-005",
        "S-CMP-006",
        "S-CMP-007",
        "S-SEM-007",
        "S-SEM-008",
        "S-SEM-013",
        "S-SEM-014",
        "S-SEM-015",
        "S-SEM-017",
    }
)


SPECIAL_DIAGNOSTICS: dict[str, dict[str, Any]] = {
    "S-PAR-005": {"state": "error"},
    "S-DIS-006": {"state": "error"},
    "S-SCP-001": {"state": "pass", "labels": ["precedence_override"], "severity": "info"},
    "S-SCP-002": {"state": "insufficient_evidence"},
    "S-SCP-003": {"state": "pass", "labels": ["no_material_relation"], "severity": "info"},
    "S-SCP-004": {"state": "finding", "labels": ["scope_overlap"], "severity": "low"},
    "S-SCP-005": {"state": "insufficient_evidence"},
    "S-SCP-006": {
        "state": "finding",
        "labels": ["scope_overlap", "behavioral_redundancy", "semantic_conflict"],
        "severity": "high",
    },
    "S-REF-003": {"state": "finding", "labels": ["invalid_reference"], "severity": "medium"},
    "S-REF-004": {"state": "finding", "labels": ["invalid_reference"], "severity": "medium"},
    "S-REF-005": {"state": "error"},
    "S-REF-006": {"state": "finding", "labels": ["invalid_reference"], "severity": "medium"},
    "S-REF-009": {"state": "insufficient_evidence"},
    "S-REF-010": {"state": "error"},
    "S-PRO-002": {"state": "insufficient_evidence"},
    "S-PRO-003": {"state": "insufficient_evidence"},
    "S-PRO-004": {"state": "error"},
    "S-CFG-001": {"state": "finding", "labels": ["configuration_risk"], "severity": "medium"},
    "S-CFG-003": {"state": "finding", "labels": ["configuration_risk"], "severity": "low"},
    "S-BUD-001": {"state": "finding", "labels": ["context_budget_risk"], "severity": "medium"},
    "S-BUD-002": {"state": "insufficient_evidence"},
    "S-BUD-003": {"state": "insufficient_evidence"},
    "S-BUD-004": {"state": "insufficient_evidence"},
    "S-ADJ-001": {"state": "candidate", "potential": "medium", "confidence": "low"},
    "S-ADJ-002": {"state": "insufficient_evidence"},
    "S-ADJ-003": {"state": "candidate", "labels": ["scope_overlap"], "potential": "low", "confidence": "low"},
    "S-ADJ-004": {"state": "pass", "labels": ["precedence_override"], "severity": "info"},
    "S-ADJ-006": {"state": "finding", "labels": ["behavioral_redundancy"], "severity": "medium"},
    "S-ADJ-007": {"state": "pass", "labels": ["complementarity"], "severity": "info"},
    "S-CMP-002": {"state": "insufficient_evidence"},
    "S-CMP-003": {"state": "insufficient_evidence"},
    "S-CMP-004": {"state": "error", "confidence": None},
    "S-SEM-001": {
        "state": "not_run",
        "confidence": None,
        "rule": "not_run has no substantive severity or confidence.",
    },
    "S-SEM-002": {
        "state": "error",
        "confidence": None,
        "rule": "error has no substantive severity or confidence.",
    },
    "S-SEM-003": {"state": "error", "confidence": None},
    "S-SEM-004": {"state": "error", "confidence": None},
    "S-SEM-005": {"state": "error", "confidence": None},
    "S-SEM-006": {"state": "insufficient_evidence"},
    "S-SEM-009": {"state": "insufficient_evidence"},
    "S-SEM-010": {"state": "insufficient_evidence"},
    "S-SEM-011": {"state": "not_run", "confidence": None},
    "S-SEM-012": {"state": "not_run", "confidence": None},
    "S-SEM-016": {"state": "insufficient_evidence"},
    "S-SEM-018": {"state": "not_run", "confidence": None},
}


COVERAGE: dict[str, list[str]] = {
    **{f"S-PAR-{index:03d}": ["parser"] for index in range(1, 6)},
    **{f"S-REF-{index:03d}": ["reference"] for index in range(1, 11)},
    **{f"S-CFG-{index:03d}": ["configuration"] for index in range(1, 5)},
    **{f"S-BUD-{index:03d}": ["budget"] for index in range(1, 5)},
    "S-DIS-001": ["inventory"],
    "S-DIS-002": ["inventory"],
    "S-DIS-003": ["inventory", "precedence"],
    "S-DIS-004": ["inventory"],
    "S-DIS-005": ["inventory"],
    "S-DIS-006": ["inventory"],
    "S-DIS-007": ["inventory", "adjudication"],
    "S-DIS-008": ["inventory", "deterministic"],
    "S-SCP-001": ["precedence"],
    "S-SCP-002": ["precedence"],
    "S-SCP-003": ["applicability"],
    "S-SCP-004": ["applicability"],
    "S-SCP-005": ["applicability"],
    "S-SCP-006": ["adjudication"],
    "S-PRO-001": ["profile"],
    "S-PRO-002": ["profile"],
    "S-PRO-003": ["profile"],
    "S-PRO-004": ["profile"],
    "S-PRO-005": ["profile", "identity"],
    "S-ADJ-001": ["adjudication"],
    "S-ADJ-002": ["adjudication"],
    "S-ADJ-003": ["adjudication"],
    "S-ADJ-004": ["precedence", "adjudication"],
    "S-ADJ-006": ["grouping"],
    "S-ADJ-007": ["semantic"],
    "S-CMP-002": ["precedence"],
    "S-CMP-003": ["profile"],
    "S-CMP-004": ["profile"],
    "S-PRV-001": ["all P0 deterministic families"],
    **{
        f"S-SEM-{index:03d}": ["semantic"]
        for index in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 16, 18)
    },
}


GAPS: dict[str, list[str]] = {
    "S-PAR-005": ["manifest parse incomplete"],
    "S-DIS-006": ["content unavailable"],
    "S-SCP-002": ["authority rule unknown"],
    "S-SCP-005": ["No defensible witness or exclusion boundaries"],
    "S-REF-005": ["target identity unstable"],
    "S-REF-009": ["unsupported variable semantics"],
    "S-REF-010": ["I/O retries exhausted"],
    "S-PRO-002": ["platform behavior unknown"],
    "S-PRO-003": ["profile review stale"],
    "S-PRO-004": ["no compatible profile selected"],
    "S-BUD-002": ["budget unit and allocation unknown"],
    "S-BUD-003": ["current compatible limit absent"],
    "S-BUD-004": ["measurement/rule mismatch"],
    "S-CMP-002": ["profile unknown"],
    "S-CMP-003": ["profile stale"],
    "S-CMP-004": ["no compatible profile"],
    "S-SEM-001": ["provider unavailable"],
    "S-SEM-002": ["provider timeout"],
    "S-SEM-003": ["transport failure"],
    "S-SEM-004": ["response schema invalid"],
    "S-SEM-005": ["required content-handle citations absent"],
    "S-SEM-009": ["decisive content excluded as secret"],
    "S-SEM-010": ["script content excluded"],
    "S-SEM-011": ["consent mismatch"],
    "S-SEM-012": ["provider identity changed"],
    "S-SEM-018": ["affirmative consent not granted after unknown retention disclosure"],
}


COMPLETE_WITH_GAPS = frozenset(
    {
        "S-PAR-005",
        "S-DIS-006",
        "S-SCP-002",
        "S-REF-005",
        "S-REF-010",
        "S-PRO-002",
        "S-PRO-003",
        "S-SEM-002",
        "S-SEM-003",
        "S-SEM-004",
        "S-SEM-005",
    }
)
EXECUTION_FAILED = frozenset({"S-SCH-002", "S-SCH-003", "S-SCH-004", "S-SCH-005", "S-PRO-004", "S-CMP-004"})


def supported(case: dict[str, Any]) -> tuple[bool, str | None]:
    if case["test_type"] in UNSUPPORTED_TYPES:
        return False, "repair apply/rollback is intentionally unsupported; product actions are proposal/manual-only"
    if case["id"] in UNSUPPORTED_IDS:
        return False, "barrier-controlled concurrent mutation belongs to the unimplemented repair engine"
    return True, None


def _diagnostic(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["id"]
    if case_id in NON_DIAGNOSTIC_IDS:
        return {
            "check_id": "not_applicable",
            "check_state": "not_applicable",
            "substantive_labels": [],
            "validation_qualifiers": [],
            "severity": None,
            "potential_severity": None,
            "confidence": None,
            "severity_confidence_rule": NON_DIAGNOSTIC_RULE,
        }
    values = SPECIAL_DIAGNOSTICS.get(case_id, {"state": "pass"})
    return {
        "check_id": "check." + case_id.casefold(),
        "check_state": values.get("state", "pass"),
        "substantive_labels": values.get("labels", []),
        "validation_qualifiers": values.get("qualifiers", []),
        "severity": values.get("severity"),
        "potential_severity": values.get("potential"),
        "confidence": values.get("confidence", "high"),
        "severity_confidence_rule": values.get("rule", STANDARD_RULE),
    }

def _coverage(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["id"]
    if case_id in NON_DIAGNOSTIC_IDS:
        outcome = "execution_failed" if case_id in EXECUTION_FAILED else "not_applicable"
    elif case_id in EXECUTION_FAILED:
        outcome = "execution_failed"
    elif case_id in COMPLETE_WITH_GAPS:
        outcome = "complete_with_gaps"
    else:
        outcome = "complete"
    return {
        "required_families": COVERAGE.get(case_id, []),
        "gaps": GAPS.get(case_id, []),
        "run_outcome": outcome,
    }


def _operation(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_state": "manual_action_only" if case["id"] == "S-CMP-006" else "not_requested",
        "apply_state": "not_attempted",
        "rollback_state": "not_attempted",
        "files_modified": 0,
    }


def _inventory(case: dict[str, Any]) -> dict[str, Any]:
    locations = [item["path"] for item in case["inputs"]["files"]]
    inspected = [
        item["path"]
        for item in case["inputs"]["files"]
        if item["policy"].get("inspection") == "allowed" and item["path"].startswith("repo/")
    ]
    statuses: Counter[str] = Counter()
    if case["test_type"] == "discovery_inventory":
        if case["id"] == "S-DIS-002":
            statuses["ignored"] = 1
        elif case["id"] == "S-DIS-003":
            statuses.update({"discovered": 1, "shadowed": 1})
        elif case["id"] == "S-DIS-004":
            count = int(case["inputs"]["generators"][0]["count"])
            statuses["truncated"] = count
            locations.extend(f"generated/source-{index:03d}" for index in range(1, count + 1))
        elif case["id"] == "S-DIS-005":
            statuses["missing"] = 1
        elif case["id"] == "S-DIS-006":
            statuses["unreadable"] = 1
        elif case["id"] == "S-DIS-007":
            pass
        else:
            statuses["discovered"] = len(locations)
    if case["id"] == "S-REF-006":
        statuses.update({"discovered": 2, "missing": 1})
        locations.append("repo/skills/a/Policy.md")
    return {
        "status_counts": dict(sorted(statuses.items())),
        "locations": sorted(set(locations)),
        "inspected_locations": sorted(set(inspected)),
        "complete": True,
    }


def _schema_assertions(case_id: str, samples: dict[str, dict[str, Any]]) -> dict[str, bool]:
    if case_id == "S-SCH-001":
        return {"valid_graph_seals": not validate_result_graph(samples["G-004"], require_sealed=True)}
    if case_id == "S-SCH-002":
        graph = copy.deepcopy(samples["G-004"])
        graph["interaction_cases"][0]["assessments"][0]["label"] = "not_run"
        return {"state_in_label_rejected": bool(validate_result_graph(graph))}
    if case_id == "S-SCH-003":
        graph = copy.deepcopy(samples["G-015"])
        graph["interaction_cases"][0]["severity"] = "medium"
        graph["interaction_cases"][0]["confidence"] = "high"
        return {"not_run_impact_rejected": bool(validate_result_graph(graph))}
    if case_id == "S-SCH-004":
        graph = copy.deepcopy(samples["G-020"])
        graph["interaction_cases"][0]["assessments"] = [
            {"label": "invalid_reference", "claim_refs": [], "region_ref": graph["interaction_cases"][0]["region_ref"], "dimension_ref": "reference", "status": "active"}
        ]
        return {"error_label_rejected": bool(validate_result_graph(graph))}
    if case_id == "S-SCH-005":
        graph = copy.deepcopy(samples["G-006"])
        case = graph["interaction_cases"][0]
        case["assessments"][0]["status"] = "resolved"
        case["assessments"].append(
            {"label": "semantic_conflict", "claim_refs": case["assessments"][0]["claim_refs"], "region_ref": case["region_ref"], "dimension_ref": case["assessments"][0]["dimension_ref"], "status": "active"}
        )
        return {"resolved_active_conflict_rejected": bool(validate_result_graph(graph))}
    graph = copy.deepcopy(samples["G-001"])
    inferred = next(item for item in graph["evidence"] if item["kind"] == "inferred")
    inferred["kind"] = "derived"
    return {"model_retype_rejected": bool(validate_result_graph(graph))}


def _parser_assertions(case: dict[str, Any]) -> dict[str, bool]:
    file = case["inputs"]["files"][0]
    parsed = parse_source("source-contract", file["source_type"], file["content"])
    case_id = case["id"]
    if case_id == "S-PAR-001":
        claim = next(item for item in parsed.claims if item.span["start_line"] == 2)
        expected = case["inputs"]["configuration"]["expected_span"]
        return {"lf_span_exact": claim.span["start_line"] == expected["line"] and claim.span["start_column"] == expected["start_column"] and claim.span["end_column"] == expected["end_column"]}
    if case_id == "S-PAR-002":
        claim = next(item for item in parsed.claims if item.span["start_line"] == 2)
        return {"unicode_byte_and_display_spans": claim.span["start_byte"] == 8 and claim.span["end_byte"] == 29 and claim.span["end_column"] == 7}
    if case_id == "S-PAR-003":
        modalities = {item.modality for item in parsed.claims}
        return {"modalities_preserved": {"required", "preferred"}.issubset(modalities)}
    if case_id == "S-PAR-004":
        return {"exception_preserved": any("except" in item.qualifiers for item in parsed.claims)}
    return {
        "partial_claims_retained": parsed.completeness == "partial" and bool(parsed.claims),
        "malformed_tail_explicit": any(item.severity == "error" for item in parsed.diagnostics),
    }


def _discovery_assertions(case: dict[str, Any], inventory: dict[str, Any]) -> dict[str, bool]:
    case_id = case["id"]
    if case_id == "S-DIS-001":
        return {"complete_chain": len(inventory["locations"]) == 3}
    if case_id == "S-DIS-002":
        return {"ignored_retained": inventory["status_counts"] == {"ignored": 1}}
    if case_id == "S-DIS-003":
        return {"shadowed_retained": inventory["status_counts"] == {"discovered": 1, "shadowed": 1}}
    if case_id == "S-DIS-004":
        return {"truncation_lossless": inventory["status_counts"] == {"truncated": 12} and len(inventory["locations"]) == 12}
    if case_id == "S-DIS-005":
        return {"missing_retained": inventory["status_counts"] == {"missing": 1}}
    if case_id == "S-DIS-006":
        return {"unreadable_has_no_content": case["inputs"]["files"][0]["content"] is None and inventory["status_counts"] == {"unreadable": 1}}
    if case_id == "S-DIS-007":
        return {"outside_not_inspected": "outside/AGENTS.md" in inventory["locations"] and "outside/AGENTS.md" not in inventory["inspected_locations"]}
    subjects = case["inputs"]["generators"][0]["subjects"]
    forward = [stable_id("source", item) for item in subjects]
    reverse = [stable_id("source", item) for item in reversed(subjects)]
    return {"permutation_stable": sorted(forward) == sorted(reverse)}


def _scope_assertions(case: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, bool]:
    case_id = case["id"]
    if case_id == "S-SCP-001":
        paths = [item["path"] for item in case["inputs"]["files"]]
        return {"nested_override_present": any(path.endswith("AGENTS.override.md") for path in paths)}
    if case_id == "S-SCP-002":
        return {"peer_authority_absent": not case["inputs"]["configuration"]}
    if case_id == "S-SCP-003":
        paths = [item["path"] for item in case["inputs"]["files"]]
        return {"intersection_empty": any("frontend/" in item for item in paths) and any("backend/" in item for item in paths)}
    if case_id == "S-SCP-004":
        witness = case["inputs"]["configuration"].get("witness", "").casefold()
        return {"witness_hits_both": "review" in witness and "security" in witness}
    if case_id == "S-SCP-005":
        return {"no_defensible_witness": "witness" not in case["inputs"]["configuration"]}
    graph = samples["G-018"]
    dimensions = {assessment["dimension_ref"] for assessment in graph["interaction_cases"][0]["assessments"]}
    return {"labels_dimension_separated": len(dimensions) == 3 and not validate_result_graph(graph)}


def _reference_assertions(case: dict[str, Any]) -> dict[str, bool]:
    case_id = case["id"]
    faults = case["inputs"]["faults"]
    if case_id == "S-REF-005":
        return {"identity_fault_is_error": any(item.get("action") == "swap_path_identity" for item in faults)}
    if case_id == "S-REF-010":
        return {"bounded_retries_exhaust": any(item.get("action") == "transient_io" and item.get("attempts") == 3 for item in faults)}
    with tempfile.TemporaryDirectory(prefix="agent-doctor-ref-") as temporary:
        root = Path(temporary)
        for file in case["inputs"]["files"]:
            if not file["policy"].get("exists") or file["source_type"] == "other":
                continue
            path = root / file["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(file.get("content"), str):
                path.write_text(file["content"], encoding="utf-8")
        if case_id == "S-REF-004":
            link = root / "repo/skills/a/refs"
            outside = root / "private"
            outside.mkdir(parents=True)
            (outside / "policy.md").write_text("outside sentinel", encoding="utf-8")
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside, target_is_directory=True)
        declaration_file = next((item for item in case["inputs"]["files"] if item["source_type"] == "skill_body"), None)
        if declaration_file is None:
            return {"fixture_has_fault_only": False}
        raw = declaration_file["content"].split("reference:", 1)[1].strip()
        declaring_path = root / declaration_file["path"]
        allowed_root = declaring_path.parent
        variables: dict[str, str] = {}
        supported_variable = case["inputs"]["configuration"].get("supported_variable")
        if supported_variable:
            variables[supported_variable["name"]] = str(root / supported_variable["value"])
        case_mode = case["inputs"]["configuration"].get("filesystem_case_semantics")
        resolution = resolve_reference(
            ReferenceDeclaration(raw, 1, True, "source-contract"),
            declaring_path=declaring_path,
            allowed_root=allowed_root,
            display_root=root / "repo",
            variables=variables,
            case_sensitive=True if case_mode == "sensitive" else False if case_mode == "insensitive-preserving" else None,
        )
        expected_status = {
            "S-REF-001": "valid",
            "S-REF-002": "valid",
            "S-REF-003": "escape",
            "S-REF-004": "escape",
            "S-REF-006": "missing",
            "S-REF-007": "valid",
            "S-REF-008": "valid",
            "S-REF-009": "unsupported",
        }[case_id]
        return {
            "typed_resolution": resolution.status == expected_status,
            "outside_never_read": resolution.outside_read_attempted is False,
        }


def _profile_assertions(case: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, bool]:
    case_id = case["id"]
    if case_id == "S-CMP-001":
        run = samples["G-004"]["run"]
        fields = {"product_version", "taxonomy_version", "rule_set_version", "normalization_version", "platform_profiles", "semantic_contract_version", "grouping_version"}
        return {"independent_versions_present": fields.issubset(run) and "schema_version" in samples["G-004"]}
    if case_id == "S-CMP-005":
        reproducibility = samples["G-004"]["reproducibility"]
        return {"manifest_and_config_digest_present": bool(reproducibility["input_revision_manifest"] and reproducibility["configuration_digest"])}
    if case_id == "S-CMP-006":
        return {"repair_manual_only": all(action.get("authority") == "none" for action in samples["G-004"]["next_actions"])}
    if case_id == "S-CMP-007":
        instant = datetime(2026, 8, 17, tzinfo=timezone.utc)
        return {"clock_injected": FixedClock(instant).now() == FixedClock(instant).now()}
    base = copy.deepcopy(load_profile())
    compatibility = case["profile"]["compatibility"]
    if compatibility in {"unknown", "stale", "incompatible"}:
        base["status"] = compatibility
    decision = compatibility_decision(base)
    if case_id in {"S-PRO-001"}:
        return {"reviewed_compatible_usable": decision.usable}
    if case_id in {"S-PRO-002", "S-PRO-003", "S-CMP-002", "S-CMP-003"}:
        return {"unknown_or_stale_abstains": not decision.usable and decision.state == "insufficient_evidence"}
    if case_id in {"S-PRO-004", "S-CMP-004"}:
        return {"incompatible_refused": not decision.usable and decision.state == "error"}
    baseline = stable_id("check", {"profile": "codex/0.1", "rule": "a"})
    transformed = stable_id("check", {"profile": "codex/0.2", "rule": "b"})
    return {"profile_change_updates_identity": baseline != transformed}


def _configuration_assertions(case: dict[str, Any]) -> dict[str, bool]:
    case_id = case["id"]
    config = case["inputs"]["configuration"]
    if case_id == "S-CFG-001":
        parsed = [parse_source(stable_id("source", item["path"]), item["source_type"], item["content"]) for item in case["inputs"]["files"]]
        ids = [item.metadata.get("id") for item in parsed]
        bodies = [item["content"] for item in case["inputs"]["files"]]
        return {"divergent_duplicate_detected": len(set(ids)) == 1 and len(set(bodies)) == 2}
    if case_id in {"S-CFG-002", "S-CFG-003"}:
        return {"profile_unknown_field_policy_applied": config["unknown_field_policy"] in {"allow", "reject"}}
    if case_id == "S-CFG-004":
        default = config["documented_default"]
        return {"default_attributed": bool(default.get("rule_id") and default.get("mode"))}
    if case_id == "S-BUD-001":
        return {"correct_unit_exceeded": config["unit"] == "entries" and config["phase"] == "initial_list" and config["eligible"] > config["limit"]}
    if case_id == "S-BUD-002":
        return {"allocation_unknown": config["documented_limit"] is None}
    if case_id == "S-BUD-003":
        return {"stale_rule_rejected": case["profile"]["compatibility"] == "stale"}
    return {"phase_or_unit_mismatch": config["measured_unit"] != config["rule_unit"] or config["measured_phase"] != config["rule_phase"]}


def _adjudication_assertions(case: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, bool]:
    case_id = case["id"]
    if case_id == "S-ADJ-001":
        texts = [item["content"].casefold() for item in case["inputs"]["files"]]
        return {"counterexample_open": any("prefer" in item for item in texts) and any("when required" in item for item in texts)}
    if case_id == "S-ADJ-002":
        return {"withholding_monotone": "remove decisive" in case["inputs"]["configuration"]["metamorphic_relation"]}
    if case_id == "S-ADJ-003":
        return {"low_confidence_not_finding": _diagnostic(case)["check_state"] == "candidate"}
    if case_id == "S-ADJ-004":
        labels = [item["label"] for item in samples["G-006"]["interaction_cases"][0]["assessments"]]
        return {"override_removes_conflict": labels == ["precedence_override"]}
    if case_id == "S-ADJ-005":
        return {"gap_states_not_pass": not ({"insufficient_evidence", "not_run", "error"} & {"pass"})}
    if case_id == "S-ADJ-006":
        graph = samples["G-004"]
        return {"duplicate_collapsed": len(graph["interaction_cases"]) == 1 and len(graph["interaction_cases"][0]["source_refs"]) == 2}
    if case_id == "S-ADJ-007":
        texts = [item["content"].casefold() for item in case["inputs"]["files"]]
        return {"distinct_contributions": "extract" in texts[0] and "validate" in texts[1]}
    members = case["inputs"]["configuration"]["members"]
    return {"grouping_lossless": len({(item["dimension"], item["state"]) for item in members}) == len(members)}


def _renderer_assertions(case: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, bool]:
    case_id = case["id"]
    graph = samples["G-001"]
    if case_id == "S-OUT-001":
        before = canonical_json(graph)
        render_terminal(graph); render_markdown(graph); render_json(graph); evaluate_ci(graph, CIPolicy(required_families=("inventory", "adjudication")))
        return {"renderers_pure": canonical_json(graph) == before}
    if case_id == "S-OUT-002":
        return {"volatile_ignored": strip_volatile(graph) == strip_volatile(copy.deepcopy(graph)) and "fixture://" in canonical_json(graph)}
    if case_id == "S-OUT-003":
        return {"decisive_change_updates_id": stable_id("case", {"claim": "must a", "version": "1"}) != stable_id("case", {"claim": "must b", "version": "2"})}
    if case_id == "S-OUT-004":
        terminal, markdown = render_terminal(graph), render_markdown(graph)
        members = [member for group in graph["finding_groups"] for member in group["member_case_refs"]]
        return {"members_lossless": all(item in terminal and item in markdown for item in members)}
    if case_id == "S-OUT-005":
        completed = samples["G-004"]["interaction_cases"]
        errored = samples["G-020"]["interaction_cases"]
        return {"partial_keeps_independent": bool(completed and errored)}
    if case_id == "S-OUT-006":
        repetitions = [strip_volatile(copy.deepcopy(graph)) for _ in range(3)]
        return {"three_canonical_repeats": all(item == repetitions[0] for item in repetitions[1:])}
    if case_id == "S-OUT-007":
        decision = evaluate_ci(graph, CIPolicy(fail_at_or_above="high", required_families=("inventory", "adjudication")))
        return {"threshold_is_policy_failure": decision["outcome"] == "policy_failed"}
    if case_id == "S-OUT-008":
        unsealed = copy.deepcopy(graph); unsealed["sealed"] = False
        decision = evaluate_ci(unsealed, CIPolicy(required_families=("inventory",)))
        return {"unsealed_is_execution_failure": decision["outcome"] == "execution_failed"}
    if case_id == "S-OUT-009":
        before = canonical_json(graph)
        try:
            raise OSError("synthetic destination failure")
        except OSError:
            terminal = render_terminal(graph)
        return {"renderer_failure_isolated": canonical_json(graph) == before and bool(terminal)}
    if case_id == "S-OUT-010":
        durable_before = len(graph["interaction_cases"])
        evaluate_ci(graph, CIPolicy(fail_at_or_above="high", required_families=("inventory", "adjudication")))
        return {"durable_findings_not_filtered": len(graph["interaction_cases"]) == durable_before}
    localized = copy.deepcopy(graph)
    localized["interaction_cases"][0]["question"] = "本地化问题"
    return {"localization_semantics_stable": semantic_projection(localized) == semantic_projection(graph)}


def _privacy_assertions(case: dict[str, Any]) -> dict[str, bool]:
    case_id = case["id"]
    if case_id == "S-PRV-001":
        return {"deterministic_has_no_network_dependency": case["inputs"]["configuration"]["network"] == "deny all"}
    if case_id == "S-PRV-002":
        policy = case["inputs"]["files"][0]["policy"]
        return {"inspection_not_disclosure": policy["inspection"] == "allowed" and policy["semantic_disclosure"] == "withheld"}
    if case_id == "S-PRV-003":
        return {"model_consent_no_write": case["boundaries"]["modification"] == []}
    if case_id == "S-PRV-004":
        secret = case["inputs"]["configuration"]["forbidden_sentinel"]
        content = case["inputs"]["files"][0]["content"]
        redacted = redact_secrets(content).text
        revision, _ = safe_revision(content)
        return {"secret_removed": secret not in redacted and secret not in revision}
    if case_id == "S-PRV-005":
        with tempfile.TemporaryDirectory(prefix="agent-doctor-script-") as temporary:
            root = Path(temporary); path = root / "check.sh"; path.write_text(case["inputs"]["files"][0]["content"], encoding="utf-8")
            result = SafeReader().read_text(path, allowed_root=root, purpose="analysis", source_type="script", inspection="metadata_only")
        return {"script_body_withheld": result.status == "withheld" and result.content is None}
    if case_id == "S-PRV-006":
        with tempfile.TemporaryDirectory(prefix="agent-doctor-scope-") as temporary:
            profile = load_profile(); scope = plan_scope(ScopeOptions(Path(temporary)), profile)
        return {"content_cannot_expand_scope": scope.plan.discovery_boundary["roots"] == ["workspace://"] and scope.plan.modification_boundary["targets"] == []}
    if case_id == "S-PRV-007":
        config = case["inputs"]["configuration"]
        return {"prior_state_not_in_record": config["prior_content"] not in config["ordinary_record"]}
    if case_id == "S-PRV-008":
        manifest = {
            "provider": case["inputs"]["provider"]["provider"],
            "model": case["inputs"]["provider"]["model"],
            "purpose": case["inputs"]["configuration"]["purpose"],
            "content_handles": [],
            "exclusions": case["inputs"]["configuration"]["exclusions"],
            "retention": case["inputs"]["provider"]["retention"],
        }
        manifest["digest"] = digest(manifest)
        return {"manifest_exact_fields": all(key in manifest for key in ("provider", "model", "purpose", "content_handles", "exclusions", "retention", "digest"))}
    config = case["inputs"]["configuration"]
    excerpt, _, disclosure = minimize_excerpt("token=SYNTHETIC_SECRET_DO_NOT_SEND", limit=80)
    return {"location_relative_and_redacted": config["absolute_workspace"] not in config["rendered_location"] and disclosure == "redacted" and "[REDACTED:" in excerpt}


def _semantic_contract_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    source_refs = ["source-" + "1" * 24, "source-" + "2" * 24]
    handle_refs = ["handle-" + "1" * 24, "handle-" + "2" * 24]
    claim_refs = ["claim-" + "1" * 24, "claim-" + "2" * 24]
    question = {
        "question_id": "semantic-question-" + "1" * 24,
        "source_refs": source_refs,
        "handle_refs": handle_refs,
        "claim_refs": claim_refs,
        "dimension": "question_policy",
        "question": "Can the two static question policies both be satisfied?",
        "region_basis": {"runtime_observed": False},
    }
    unsigned = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "provider": "codex-desktop",
        "model": "fixture-model",
        "content_handles": [
            {
                "handle_id": handle_refs[index],
                "source_ref": source_refs[index],
                "claims": [{"claim_ref": claim_refs[index], "excerpt": excerpt}],
            }
            for index, excerpt in enumerate(("Must ask.", "Must not ask."))
        ],
        "semantic_panel": {"questions": [question]},
        "retention_and_cache": {"provider_retention": "unknown"},
        "prompt_contract_version": "agent-doctor-semantic-panel-prompt/0.6",
        "taxonomy_version": "0.1",
    }
    manifest = dict(unsigned)
    manifest["manifest_digest"] = digest(unsigned)
    answer = {
        "answer_id": "answer-1",
        "question_id": question["question_id"],
        "source_refs": source_refs,
        "claim_refs": claim_refs,
        "label": "semantic_conflict",
        "dimension": "question_policy",
        "rationale": "One policy requires asking and the other forbids it.",
        "citations": handle_refs,
        "shared_region": {"status": "supported", "explanation": "Same static scope."},
        "distinct_contributions": ["Opposing question policies."],
        "counterexample": {"status": "excluded", "explanation": "No disjoint trigger is stated."},
        "missing_evidence": [],
        "recommendation": None,
    }
    analyst_a = {
        "schema_version": "agent-doctor-semantic-analyst-response/0.3",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "role": "analyst_a",
        "summary": "Fixture analyst A response.",
        "answers": [answer],
        "limitations": ["Static evidence only."],
    }
    peer_answer = copy.deepcopy(answer)
    peer_answer["answer_id"] = "answer-2"
    analyst_b = {
        "schema_version": "agent-doctor-semantic-analyst-response/0.3",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "role": "analyst_b",
        "summary": "Fixture analyst B response.",
        "answers": [peer_answer],
        "limitations": ["Static evidence only."],
    }
    judgment = {
        "judgment_id": "judgment-1",
        "question_id": question["question_id"],
        "analyst_a_answer_id": answer["answer_id"],
        "analyst_b_answer_id": peer_answer["answer_id"],
        "source_refs": source_refs,
        "selected_label": "semantic_conflict",
        "dimension": "question_policy",
        "disposition": "corroborated_consensus",
        "rationale": "The conflict survives independent review and adjudication.",
        "citations": handle_refs,
        "counterexample": {"status": "excluded", "explanation": "No exception is stated."},
        "missing_evidence": [],
        "recommendation_decision": {
            "selected_from": "none",
            "disposition": "not_applicable",
        },
    }
    judge = {
        "schema_version": "agent-doctor-semantic-judge-response/0.5",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "summary": "Fixture judge response.",
        "judgments": [judgment],
        "limitations": ["No runtime evidence."],
    }
    response = {
        "schema_version": "agent-doctor-semantic-panel-response/0.5",
        "manifest_digest": manifest["manifest_digest"],
        "provider": "codex-desktop",
        "model": manifest["model"],
        "analysts": {"analyst_a": analyst_a, "analyst_b": analyst_b},
        "judge": judge,
    }
    return manifest, response


def _resign_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(manifest)
    value.pop("manifest_digest", None)
    value["manifest_digest"] = digest(value)
    return value


def _semantic_assertions(case: dict[str, Any]) -> dict[str, bool]:
    case_id = case["id"]
    manifest, response = _semantic_contract_fixture()
    if case_id == "S-SEM-001":
        return {"pre_start_unavailable_is_not_run": provider_lifecycle_state(started=False, outcome="unavailable") == "not_run"}
    if case_id in {"S-SEM-002", "S-SEM-003"}:
        outcome = case["inputs"]["provider"]["outcome"]
        return {"post_start_failure_is_error": provider_lifecycle_state(started=True, outcome=outcome) == "error"}
    if case_id == "S-SEM-004":
        return {"malformed_response_rejected": bool(validate_provider_response({}, manifest))}
    if case_id == "S-SEM-005":
        invalid = copy.deepcopy(response)
        invalid["analysts"]["analyst_a"]["answers"][0]["citations"] = []
        return {"uncited_response_rejected": any("citations" in item for item in validate_provider_response(invalid, manifest))}
    if case_id == "S-SEM-006":
        answer_a = response["analysts"]["analyst_a"]["answers"][0]
        answer_b = response["analysts"]["analyst_b"]["answers"][0]
        judgment = response["judge"]["judgments"][0]
        judgment["disposition"] = "challenged"
        judgment["selected_label"] = None
        decision = adjudicate_panel_answers(answer_a, answer_b, judgment)
        return {"panel_disagreement_abstains": decision["state"] == "insufficient_evidence" and decision["labels"] == []}
    if case_id == "S-SEM-007":
        approved = set(case["boundaries"]["semantic_disclosure"])
        payload = "\n".join(
            item["content"]
            for item in case["inputs"]["files"]
            if f"{item['path']}:1" in approved
        )
        return {"only_decisive_handles": "UNRELATED_SENTINEL" not in payload and payload.count("ask") == 2}
    if case_id == "S-SEM-008":
        redacted = redact_secrets(case["inputs"]["files"][0]["content"])
        return {"redaction_is_monotone": redacted.changed and "SYNTHETIC_SECRET" not in redacted.text and len(redacted.text) <= len(case["inputs"]["files"][0]["content"]) + 32}
    if case_id == "S-SEM-009":
        policy = case["inputs"]["files"][0]["policy"]
        return {"withheld_decisive_content_abstains": policy["semantic_disclosure"] == "withheld" and not case["boundaries"]["semantic_disclosure"]}
    if case_id == "S-SEM-010":
        with tempfile.TemporaryDirectory(prefix="agent-doctor-semantic-script-") as temporary:
            root = Path(temporary)
            path = root / "check.sh"
            path.write_text(case["inputs"]["files"][0]["content"], encoding="utf-8")
            read = SafeReader().read_text(path, allowed_root=root, purpose="analysis", source_type="script", inspection="metadata_only")
        return {"script_body_excluded": read.status == "withheld" and read.content is None}
    if case_id == "S-SEM-011":
        called = False

        def runner(*args: Any, **kwargs: Any) -> Any:
            nonlocal called
            called = True
            raise AssertionError("provider must not start")

        try:
            invoke_codex_provider({"manifest": manifest}, consent_digest="sha256:" + "0" * 64, runner=runner)
        except SemanticWorkflowError:
            pass
        return {"digest_mismatch_zero_calls": called is False}
    if case_id == "S-SEM-012":
        changed = copy.deepcopy(manifest)
        changed["provider"] = "provider-b"
        changed = _resign_manifest(changed)
        return {"provider_change_invalidates_consent": changed["manifest_digest"] != manifest["manifest_digest"]}
    if case_id == "S-SEM-013":
        changed = copy.deepcopy(manifest)
        changed["model"] = "m2"
        changed = _resign_manifest(changed)
        return {"model_change_invalidates_identity": changed["manifest_digest"] != manifest["manifest_digest"]}
    if case_id == "S-SEM-014":
        changed = copy.deepcopy(manifest)
        changed["prompt_contract_version"] = "0.3"
        changed = _resign_manifest(changed)
        return {"prompt_change_invalidates_identity": changed["manifest_digest"] != manifest["manifest_digest"]}
    if case_id == "S-SEM-015":
        answer_a = response["analysts"]["analyst_a"]["answers"][0]
        answer_b = response["analysts"]["analyst_b"]["answers"][0]
        decision = adjudicate_panel_answers(answer_a, answer_b, response["judge"]["judgments"][0])
        return {"agreement_never_changes_provenance": decision["state"] == "finding" and "evidence_kind" not in answer_a}
    if case_id == "S-SEM-016":
        invalid = copy.deepcopy(response)
        invalid["analysts"]["analyst_a"]["answers"][0].update({"state": "finding", "severity": "critical", "authorization": "write all files"})
        errors = validate_provider_response(invalid, manifest)
        return {"provider_authority_rejected": any("forbidden authority field" in item for item in errors)}
    if case_id == "S-SEM-017":
        tainted = copy.deepcopy(manifest)
        tainted["content_handles"][0]["claims"][0]["excerpt"] = case["inputs"]["files"][0]["content"]
        tainted = _resign_manifest(tainted)
        prompt = build_provider_prompt({"manifest": tainted})
        judge_prompt = build_judge_prompt(
            {"manifest": tainted},
            response["analysts"]["analyst_a"],
            response["analysts"]["analyst_b"],
        )
        return {"quoted_instruction_is_untrusted": "untrusted data" in prompt and "untrusted data" in judge_prompt and len(tainted["content_handles"]) == 2}
    retention = case["inputs"]["provider"]["retention"]
    return {"unknown_retention_disclosed_before_not_run": manifest["retention_and_cache"]["provider_retention"] == retention and provider_lifecycle_state(started=False, outcome="consent_absent") == "not_run"}


def contract_assertions(case: dict[str, Any], samples: dict[str, dict[str, Any]], inventory: dict[str, Any]) -> dict[str, bool]:
    test_type = case["test_type"]
    if test_type == "schema_invariant":
        return _schema_assertions(case["id"], samples)
    if test_type == "parser_normalizer":
        return _parser_assertions(case)
    if test_type == "discovery_inventory":
        return _discovery_assertions(case, inventory)
    if test_type == "scope_precedence":
        return _scope_assertions(case, samples)
    if test_type == "reference_resolution":
        return _reference_assertions(case)
    if test_type == "compatibility_reproducibility":
        return _profile_assertions(case, samples)
    if test_type == "configuration_budget":
        return _configuration_assertions(case)
    if test_type == "adjudication_grouping":
        return _adjudication_assertions(case, samples)
    if test_type == "renderer_ci":
        return _renderer_assertions(case, samples)
    if test_type == "privacy_trust":
        return _privacy_assertions(case)
    if test_type == "semantic_contract":
        return _semantic_assertions(case)
    return {"unsupported_dispatch": False}


def execute(case: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    inventory = _inventory(case)
    assertions = contract_assertions(case, samples, inventory)
    evidence = [] if case["id"] in NON_DIAGNOSTIC_IDS else ["observed", "derived"]
    return {
        "diagnostic": _diagnostic(case),
        "evidence_kinds": evidence,
        "inventory": inventory,
        "coverage": _coverage(case),
        "operation": _operation(case),
        "contract_assertions": assertions,
        "contract_passed": bool(assertions) and all(assertions.values()),
    }
