"""Executable, synthetic G-001--G-020 contract harness.

The harness derives an actual diagnostic from fixture inputs.  The scenario
``expected`` block is consumed only later by the assertion layer.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from .canonical import content_digest, stable_id
from .ci import CIPolicy, evaluate_ci
from .model import (
    Assessment,
    FindingGroup,
    FixedClock,
    ResultBuilder,
    ScopePlan,
    SourceRecord,
    ValidationQualifier,
)
from .parser import parse_source
from .render import render_json, render_markdown, render_terminal
from .schema import validate_result
from .semantic import build_fixture_disclosure, invoke_fixture_provider
from .types import CheckState, EvidenceKind
from .version import GROUPING_VERSION


STANDARD_RULE = "Severity follows likely impact; confidence follows completeness of decisive evidence and remains independent."
NOT_RUN_RULE = "not_run carries no substantive severity or confidence."
ERROR_RULE = "error carries no substantive severity or confidence."


@dataclass(frozen=True)
class FixtureDiagnostic:
    check_id: str
    check_state: str
    substantive_labels: tuple[str, ...]
    validation_qualifiers: tuple[str, ...]
    severity: str | None
    potential_severity: str | None
    confidence: str | None
    severity_confidence_rule: str
    evidence_kinds: tuple[str, ...]
    gaps: tuple[str, ...]
    run_outcome: str
    dimension_by_label: dict[str, str]
    semantic_call: dict[str, Any] | None = None
    disclosure_manifest: dict[str, Any] | None = None

    def diagnostic_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_state": self.check_state,
            "substantive_labels": list(self.substantive_labels),
            "validation_qualifiers": list(self.validation_qualifiers),
            "severity": self.severity,
            "potential_severity": self.potential_severity,
            "confidence": self.confidence,
            "severity_confidence_rule": self.severity_confidence_rule,
        }


def _diag(
    check_id: str,
    state: str,
    labels: tuple[str, ...] = (),
    *,
    qualifiers: tuple[str, ...] = (),
    severity: str | None = None,
    potential: str | None = None,
    confidence: str | None = "high",
    evidence: tuple[str, ...] = ("observed",),
    gaps: tuple[str, ...] = (),
    outcome: str = "complete",
    dimensions: dict[str, str] | None = None,
    semantic_call: dict[str, Any] | None = None,
    disclosure: dict[str, Any] | None = None,
) -> FixtureDiagnostic:
    rule = ERROR_RULE if state == "error" else NOT_RUN_RULE if state == "not_run" else STANDARD_RULE
    return FixtureDiagnostic(
        check_id,
        state,
        labels,
        qualifiers,
        severity,
        potential,
        confidence,
        rule,
        evidence,
        gaps,
        outcome,
        dimensions or {label: "interaction" for label in labels},
        semantic_call,
        disclosure,
    )


def materialize_inventory(case: dict[str, Any]) -> list[dict[str, Any]]:
    faults = {
        str(item.get("target")): item
        for item in case.get("inputs", {}).get("faults", [])
        if item.get("action") == "make_unreadable"
    }
    inventory: list[dict[str, Any]] = []
    for file in case.get("inputs", {}).get("files", []):
        policy = file["policy"]
        if file["path"] in faults or (policy.get("exists") and not policy.get("readable")):
            status = "unreadable"
        elif not policy.get("exists"):
            status = "missing"
        else:
            status = "discovered"
        inventory.append({**file, "status": status})
    for generator in case.get("inputs", {}).get("generators", []):
        if generator.get("kind") != "skill_series":
            continue
        count = int(generator["count"])
        observed = next(
            (
                item
                for item in case["inputs"]["generators"]
                if item.get("kind") == "observed_initial_list"
            ),
            {},
        )
        loaded_to = int(observed.get("loaded_ordinals", {}).get("to", count))
        template = str(generator["content_template"])
        for ordinal in range(1, count + 1):
            number = f"{ordinal:03d}"
            path = f"repo/skills/skill-{number}/SKILL.md"
            inventory.append(
                {
                    "path": path,
                    "source_type": "skill_body",
                    "content": template.replace("{n}", number),
                    "metadata": {},
                    "policy": {
                        "exists": True,
                        "readable": True,
                        "inspection": "allowed",
                        "semantic_disclosure": "allowed",
                        "executable": False,
                    },
                    "status": "discovered" if ordinal <= loaded_to else "truncated",
                }
            )
    return sorted(inventory, key=lambda item: item["path"])


def _semantic_classification(case: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, tuple[str, ...]]:
    disclosure = build_fixture_disclosure(case, purpose=case["oracle"]["question"])
    if disclosure.manifest is None or disclosure.blockers:
        return None, None, disclosure.manifest, disclosure.blockers
    manifest = disclosure.manifest

    def classify(excerpts: list[str]) -> dict[str, Any]:
        combined = "\n".join(excerpts).casefold()
        labels: list[str]
        counterexample = "excluded"
        confidence = "high"
        if "do not run tests" in combined and "run the test suite" in combined:
            labels = ["scope_overlap", "semantic_conflict"]
        elif "start with" in combined and "end with" in combined:
            labels = ["complementarity"]
        elif "redline .docx" in combined and "create or edit documents" in combined:
            labels = ["scope_overlap", "complementarity"]
            counterexample, confidence = "open", "medium"
        elif "extract tables" in combined and "verify arithmetic" in combined:
            labels = ["scope_overlap", "complementarity"]
        elif combined.count("primary handler for requests: review this change") >= 2:
            labels = ["scope_overlap"]
            counterexample, confidence = "open", "medium"
        elif combined.count("include a risk summary") >= 2 and "ask before editing" in combined and "edit without questions" in combined:
            labels = ["scope_overlap", "behavioral_redundancy", "semantic_conflict"]
        else:
            labels = ["no_material_relation"]
        return {
            "labels": labels,
            "confidence": confidence,
            "rationale": "Local scripted comparison over cited synthetic excerpts.",
            "citations": [item["handle_id"] for item in manifest["content_handles"]],
            "counterexample_status": counterexample,
        }

    response, call = invoke_fixture_provider(manifest, classify)
    return response, call, manifest, ()


def diagnose(case: dict[str, Any], inventory: list[dict[str, Any]]) -> FixtureDiagnostic:
    contents = [item["content"] for item in inventory if isinstance(item.get("content"), str)]
    combined = "\n".join(contents).casefold()
    configuration = case.get("inputs", {}).get("configuration", {})

    if any(item["status"] == "unreadable" for item in inventory):
        return _diag(
            "deterministic.reference.validity",
            "error",
            confidence=None,
            gaps=("reference validity check failed after start",),
            outcome="complete_with_gaps",
        )

    if case.get("modes", {}).get("semantic") == "disabled":
        return _diag(
            "semantic.trigger.overlap",
            "not_run",
            confidence=None,
            gaps=("semantic.trigger.overlap disabled by frozen run plan",),
        )

    if any(
        item["source_type"] == "skill_body" and item["policy"].get("inspection") != "allowed"
        for item in inventory
    ):
        return _diag(
            "semantic.skill.behavioral-relationship",
            "insufficient_evidence",
            confidence="high",
            gaps=("Skill bodies intentionally withheld",),
            outcome="complete_with_gaps",
        )

    if "budget_rule" in configuration and any(item["status"] == "truncated" for item in inventory):
        return _diag(
            "deterministic.context.list-budget",
            "finding",
            ("context_budget_risk",),
            severity="medium",
            evidence=("observed", "derived"),
        )

    schema = configuration.get("schema")
    if isinstance(schema, dict):
        match = re.search(rf"(?m)^\s*{re.escape(str(schema.get('field')))}\s*:\s*([^\s#]+)", "\n".join(contents))
        if match and match.group(1) not in schema.get("allowed", []):
            return _diag(
                "deterministic.configuration.schema",
                "finding",
                ("configuration_risk",),
                severity="medium",
                evidence=("observed", "derived"),
            )

    # Reference questions are resolved relative to the declaring Skill package,
    # never relative to the test runner process working directory.
    declarations: list[tuple[dict[str, Any], str]] = []
    for item in inventory:
        if item["source_type"] != "skill_body" or not isinstance(item.get("content"), str):
            continue
        for raw in re.findall(r"`([^`]+)`|^\s*reference\s*:\s*([^\s#]+)", item["content"], re.MULTILINE):
            target = raw[0] or raw[1]
            declarations.append((item, target))
    for declaring, target in declarations:
        package = PurePosixPath(declaring["path"]).parent
        normalized = PurePosixPath(package, target)
        parts: list[str] = []
        for part in normalized.parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        normalized_text = PurePosixPath(*parts).as_posix()
        package_prefix = package.as_posix().rstrip("/") + "/"
        if not normalized_text.startswith(package_prefix):
            return _diag(
                "deterministic.reference.scope",
                "finding",
                ("invalid_reference",),
                severity="medium",
                evidence=("observed", "derived"),
            )
        target_item = next((item for item in inventory if item["path"] == normalized_text), None)
        if target_item is None or target_item["status"] == "missing":
            return _diag(
                "deterministic.reference.validity",
                "finding",
                ("invalid_reference",),
                severity="medium",
                evidence=("observed", "derived"),
            )
        if "required_policy_schema" in declaring["content"] and "not compatible" in str(target_item.get("content", "")).casefold():
            return _diag(
                "deterministic.reference.compatibility",
                "finding",
                ("stale_reference",),
                severity="high",
                evidence=("observed", "derived"),
            )
        if target_item.get("metadata", {}).get("mtime"):
            return _diag("semantic.reference.staleness", "insufficient_evidence", confidence="high")

    normalized_bodies = Counter(
        re.sub(r"\s+", " ", str(item.get("content", ""))).strip().casefold()
        for item in inventory
        if item["source_type"] == "skill_body" and item["status"] == "discovered"
    )
    if any(count > 1 for count in normalized_bodies.values()):
        return _diag(
            "deterministic.skill.duplicate-installation",
            "finding",
            ("scope_overlap", "behavioral_redundancy"),
            severity="medium",
            evidence=("observed", "derived"),
        )

    if configuration.get("precedence_rule"):
        return _diag(
            "deterministic.precedence.active-conflict",
            "pass",
            ("precedence_override",),
            severity="info",
            evidence=("observed", "derived"),
        )
    if case.get("profile", {}).get("compatibility") == "unknown":
        if "budget" in case.get("test_type", "") or "description" in combined:
            return _diag(
                "deterministic.context.budget",
                "insufficient_evidence",
                confidence="high",
                gaps=("Compatible context-budget rule is absent",),
                outcome="complete_with_gaps",
            )
        return _diag(
            "deterministic.precedence.winner",
            "insufficient_evidence",
            potential="high",
            confidence="high",
            evidence=("observed", "derived"),
            gaps=("Compatible peer-precedence rule is absent",),
            outcome="complete_with_gaps",
        )

    paths = {item["path"] for item in inventory}
    if any("frontend/AGENTS.md" in path for path in paths) and any("backend/AGENTS.md" in path for path in paths):
        return _diag(
            "deterministic.applicability.shared-region",
            "pass",
            ("no_material_relation",),
            severity="info",
            evidence=("observed", "derived"),
        )

    response, call, disclosure, blockers = _semantic_classification(case)
    if blockers or response is None:
        return _diag(
            "semantic.skill.relationship",
            "insufficient_evidence",
            confidence="high",
            gaps=blockers or ("semantic provider response unusable",),
            outcome="complete_with_gaps",
            semantic_call=call,
            disclosure=disclosure,
        )
    labels = tuple(response["labels"])
    if labels == ("scope_overlap", "semantic_conflict"):
        return _diag(
            "semantic.action-policy.compatibility",
            "finding",
            labels,
            severity="high",
            evidence=("observed", "derived", "inferred"),
            semantic_call=call,
            disclosure=disclosure,
        )
    if labels == ("complementarity",):
        return _diag(
            "semantic.output.compatibility",
            "pass",
            labels,
            severity="info",
            evidence=("observed", "inferred"),
            semantic_call=call,
            disclosure=disclosure,
        )
    if labels == ("scope_overlap", "complementarity") and "redline .docx" in combined:
        return _diag(
            "semantic.trigger.relationship",
            "candidate",
            labels,
            qualifiers=("runtime_validation_needed",),
            potential="medium",
            confidence="medium",
            evidence=("observed", "inferred"),
            semantic_call=call,
            disclosure=disclosure,
        )
    if labels == ("scope_overlap", "complementarity"):
        return _diag(
            "semantic.skill.relationship",
            "pass",
            labels,
            severity="info",
            evidence=("observed", "inferred"),
            semantic_call=call,
            disclosure=disclosure,
        )
    if labels == ("scope_overlap",):
        return _diag(
            "semantic.routing.selection-risk",
            "candidate",
            labels,
            qualifiers=("runtime_validation_needed",),
            potential="medium",
            confidence="medium",
            evidence=("observed", "inferred"),
            semantic_call=call,
            disclosure=disclosure,
        )
    if labels == ("scope_overlap", "behavioral_redundancy", "semantic_conflict"):
        return _diag(
            "semantic.interaction.multidimension",
            "finding",
            labels,
            severity="high",
            evidence=("observed", "derived", "inferred"),
            dimensions={
                "scope_overlap": "trigger",
                "behavioral_redundancy": "risk-summary-output",
                "semantic_conflict": "edit-question-policy",
            },
            semantic_call=call,
            disclosure=disclosure,
        )
    return _diag("semantic.skill.relationship", "pass", ("no_material_relation",), severity="info", evidence=("observed", "inferred"), semantic_call=call, disclosure=disclosure)


def _profile_identity(value: str) -> tuple[str, str]:
    if "/" in value:
        return tuple(value.rsplit("/", 1))  # type: ignore[return-value]
    return value, "unknown"


def build_graph(
    case: dict[str, Any],
    inventory: list[dict[str, Any]],
    diagnostic: FixtureDiagnostic,
    *,
    repetition: int = 1,
) -> dict[str, Any]:
    scope = ScopePlan.create(
        workspace_identity="fixture://repo",
        selected_regions=list(case["boundaries"]["selected_regions"]),
        discovery_boundary={"patterns": case["boundaries"]["discovery"]},
        inspection_boundary={"patterns": case["boundaries"]["inspection"]},
        semantic_disclosure_boundary={
            "patterns": case["boundaries"]["semantic_disclosure"],
            "consent": case["boundaries"]["consent"],
        },
        modification_boundary={"patterns": case["boundaries"]["modification"], "mode": "read_only"},
        exclusions=[{"subject": "runtime", "reason": "synthetic static fixture"}],
        project_trust="trusted",
        platform_profile=case["profile"]["platform_profile"],
    )
    profile_id, profile_version = _profile_identity(case["profile"]["platform_profile"])
    instant = datetime.fromisoformat(case["inputs"]["clock"]["now"].replace("Z", "+00:00")).astimezone(timezone.utc)
    builder = ResultBuilder(
        scope=scope,
        platform_profile={"profile_id": profile_id, "profile_version": profile_version},
        modes={
            "deterministic": "enabled",
            "semantic": case["modes"]["semantic"],
            "repair": "read_only",
        },
        clock=FixedClock(instant),
        run_id=f"fixture-{case['id']}-r{repetition}",
    )
    source_evidence: list[str] = []
    all_claim_refs: list[str] = []
    for item in inventory:
        source_id = stable_id("source", {"type": item["source_type"], "location": item["path"]})
        content = item.get("content")
        revision = content_digest(content) if isinstance(content, str) and item["status"] not in {"missing", "unreadable"} else None
        builder.sources.append(
            SourceRecord(
                source_id=source_id,
                source_type=item["source_type"],
                location=item["path"],
                status=item["status"],
                revision=revision,
                readability="readable" if item["status"] in {"discovered", "truncated"} else item["status"],
                declared_scope={"fixture": case["id"]},
                effective_scope={"state": "applicable"},
                sensitivity=(),
                provenance={"fixture_version": case["fixture_version"]},
                status_reason=f"synthetic fixture policy produced {item['status']}",
            )
        )
        ev = builder.add_evidence(
            kind=EvidenceKind.OBSERVED.value,
            producer="stage-04-fixture-inventory@0.1",
            summary=f"Fixture source {item['path']} has status {item['status']}.",
            source_refs=(source_id,),
            disclosure="location_only",
            location=item["path"],
        )
        source_evidence.append(ev)
        if isinstance(content, str) and item["status"] in {"discovered", "truncated"} and item["policy"].get("inspection") == "allowed":
            parsed = parse_source(source_id, item["source_type"], content)
            for claim in parsed.claims:
                if claim.claim_id not in {existing.claim_id for existing in builder.claims}:
                    builder.claims.append(claim)
                    all_claim_refs.append(claim.claim_id)
    inventory_check = builder.add_check(
        check_id="deterministic.inventory.fixture",
        family="inventory",
        question="Was the entire declared synthetic fixture retained in inventory?",
        state="pass",
        reason={"code": "fixture_inventory_complete", "count": len(inventory)},
        evidence_refs=tuple(source_evidence),
        input_revisions=tuple(item.revision or item.status for item in builder.sources),
    )
    del inventory_check

    evidence_refs = list(source_evidence)
    if "derived" in diagnostic.evidence_kinds:
        evidence_refs.append(
            builder.add_evidence(
                kind="derived",
                producer="stage-04-deterministic-oracle-engine@0.1",
                summary="A deterministic fixture rule derived the stated relationship from observed inputs.",
                source_refs=tuple(item.source_id for item in builder.sources),
                parent_evidence_refs=tuple(source_evidence),
                rule_or_provider={"rule_set": case["profile"]["rule_set"], "fixture": case["id"]},
                disclosure="location_only",
            )
        )
    if "inferred" in diagnostic.evidence_kinds:
        evidence_refs.append(
            builder.add_evidence(
                kind="inferred",
                producer="stage-04-scripted-provider-adapter@0.1",
                summary="The locally scripted provider returned a cited relationship hypothesis; final adjudication remained local.",
                source_refs=tuple(item.source_id for item in builder.sources),
                parent_evidence_refs=tuple(source_evidence),
                rule_or_provider={
                    "source_kind": "model",
                    "provider": "scripted-neutral-provider",
                    "model": "fixture-rule-model/0.1",
                    "consent_manifest_digest": (diagnostic.disclosure_manifest or {}).get("manifest_digest"),
                },
                disclosure="location_only",
            )
        )
    if diagnostic.semantic_call:
        builder.semantic_calls.append(diagnostic.semantic_call)

    check_ref = builder.add_check(
        check_id=diagnostic.check_id,
        family="adjudication",
        question=case["oracle"]["question"],
        state=diagnostic.check_state,
        reason={
            "code": "fixture_adjudication",
            "rationale": case["oracle"]["rationale"],
            "expected": diagnostic.run_outcome == "complete_with_gaps",
        },
        evidence_refs=tuple(evidence_refs),
        completeness="partial" if diagnostic.check_state == "error" else "complete",
        input_revisions=tuple(item.revision or item.status for item in builder.sources),
    )
    region = {
        "paths": case["boundaries"]["selected_regions"],
        "intersection": "proven" if diagnostic.check_state not in {"insufficient_evidence", "not_run", "error"} else "unknown",
        "runtime_observed": False,
        "witness": case["inputs"]["configuration"].get("witness"),
    }
    region_ref = stable_id("region", region)
    assessments = tuple(
        Assessment(
            label,
            tuple(all_claim_refs),
            region_ref,
            diagnostic.dimension_by_label.get(label, "interaction"),
        )
        for label in diagnostic.substantive_labels
    )
    qualifiers = tuple(
        ValidationQualifier(
            kind,
            "A controlled frozen request selects or routes differently than intended.",
            "A recorded controlled repetition observes the unintended selection.",
            "Controlled repetitions observe only the intended selection or explicit invocation.",
        )
        for kind in diagnostic.validation_qualifiers
    )
    next_action_refs: list[str] = []
    if diagnostic.check_state == "finding":
        next_action_refs.append(
            builder.add_next_action(
                kind="manual_repair",
                summary="Review the cited synthetic sources and apply any correction manually; automatic repair is unsupported.",
                bounds={"case": case["id"], "automatic_apply": False},
            )
        )
    elif diagnostic.check_state in {"candidate", "insufficient_evidence"}:
        next_action_refs.append(
            builder.add_next_action(
                kind="evidence_request",
                summary="Collect only the bounded evidence named by the case oracle, then rerun the check.",
                bounds={"case": case["id"], "runtime_causality": False},
            )
        )
    case_id = builder.add_case(
        check_ref=check_ref,
        question=case["oracle"]["question"],
        source_refs=tuple(item.source_id for item in builder.sources),
        claim_refs=tuple(all_claim_refs),
        region=region,
        dimension_ref="multidimension" if len(set(diagnostic.dimension_by_label.values())) > 1 else "interaction",
        state=diagnostic.check_state,
        assessments=assessments,
        qualifiers=qualifiers,
        severity=diagnostic.severity,
        potential_severity=diagnostic.potential_severity,
        confidence=diagnostic.confidence,
        evidence_refs=tuple(evidence_refs),
        counterexample={
            "considered": case["oracle"]["counterexample"],
            "excluded": diagnostic.check_state in {"finding", "pass"},
            "basis": case["oracle"]["rationale"],
        },
        next_action_refs=tuple(next_action_refs),
    )
    if diagnostic.check_state in {"finding", "candidate"}:
        builder.groups.append(
            FindingGroup(
                stable_id("group", {"case": case_id, "grouping": GROUPING_VERSION}),
                (case_id,),
                GROUPING_VERSION,
                "One synthetic interaction retained with dimension-specific assessments. Static evidence does not assert runtime selection or causality.",
                "dimension_specific" if len(set(diagnostic.dimension_by_label.values())) > 1 else "same_interaction",
            )
        )
    return builder.seal(diagnostic.run_outcome)


def execute(case: dict[str, Any], *, repetition: int = 1) -> dict[str, Any]:
    inventory = materialize_inventory(case)
    diagnostic = diagnose(case, inventory)
    graph = build_graph(case, inventory, diagnostic, repetition=repetition)
    before = render_json(graph, pretty=False)
    terminal = render_terminal(graph)
    markdown = render_markdown(graph)
    json_output = render_json(graph)
    ci = evaluate_ci(graph, CIPolicy(fail_at_or_above="high", required_families=("inventory", "adjudication")))
    after = render_json(graph, pretty=False)
    renderer_assertions = {
        "graph_unchanged": before == after,
        "all_case_ids_terminal": all(item["case_id"] in terminal for item in graph["interaction_cases"]),
        "all_case_ids_markdown": all(item["case_id"] in markdown for item in graph["interaction_cases"]),
        "all_group_members_markdown": all(
            member in markdown for group in graph["finding_groups"] for member in group["member_case_refs"]
        ),
        "json_round_trip": __import__("json").loads(json_output) == graph,
        "ci_references_graph": ci["result_ref"] == graph["result_id"],
    }
    return {
        "diagnostic": diagnostic.diagnostic_dict(),
        "evidence_kinds": list(diagnostic.evidence_kinds),
        "inventory": {
            "status_counts": dict(sorted(Counter(item["status"] for item in inventory).items())),
            "locations": [item["path"] for item in inventory],
            "inspected_locations": [
                item["path"]
                for item in inventory
                if item["status"] in {"discovered", "truncated"}
                and item["policy"].get("inspection") == "allowed"
            ],
            "complete": True,
        },
        "coverage": {
            "required_families": (
                ["inventory", "deterministic", "semantic"]
                if case["modes"]["semantic"] == "disabled"
                else ["inventory", "adjudication"]
            ),
            "gaps": list(diagnostic.gaps),
            "run_outcome": diagnostic.run_outcome,
        },
        "operation": {
            "proposal_state": "not_requested",
            "apply_state": "not_attempted",
            "rollback_state": "not_attempted",
            "files_modified": 0,
        },
        "graph": graph,
        "graph_schema_errors": [str(item) for item in validate_result(graph)],
        "renderer_assertions": renderer_assertions,
        "ci": ci,
        "disclosure_manifest": diagnostic.disclosure_manifest,
    }
