"""Typed canonical result graph and construction helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from .canonical import digest, stable_id
from .types import CheckState, RunOutcome
from .version import (
    GROUPING_VERSION,
    NORMALIZATION_VERSION,
    RESULT_SCHEMA_VERSION,
    RULE_SET_VERSION,
    SEMANTIC_CONTRACT_VERSION,
    TAXONOMY_VERSION,
    __version__,
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedClock:
    instant: datetime

    def now(self) -> datetime:
        if self.instant.tzinfo is None:
            return self.instant.replace(tzinfo=timezone.utc)
        return self.instant.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ScopePlan:
    scope_id: str
    workspace_identity: str
    selected_regions: tuple[str, ...]
    discovery_boundary: dict[str, Any]
    inspection_boundary: dict[str, Any]
    semantic_disclosure_boundary: dict[str, Any]
    modification_boundary: dict[str, Any]
    exclusions: tuple[dict[str, str], ...]
    project_trust: str
    platform_profile: str

    @classmethod
    def create(
        cls,
        *,
        workspace_identity: str,
        selected_regions: list[str],
        discovery_boundary: dict[str, Any],
        inspection_boundary: dict[str, Any],
        semantic_disclosure_boundary: dict[str, Any],
        modification_boundary: dict[str, Any],
        exclusions: list[dict[str, str]],
        project_trust: str,
        platform_profile: str,
    ) -> "ScopePlan":
        identity = {
            "workspace_identity": workspace_identity,
            "selected_regions": selected_regions,
            "discovery_boundary": discovery_boundary,
            "inspection_boundary": inspection_boundary,
            "semantic_disclosure_boundary": semantic_disclosure_boundary,
            "modification_boundary": modification_boundary,
            "exclusions": exclusions,
            "project_trust": project_trust,
            "platform_profile": platform_profile,
        }
        return cls(
            scope_id=stable_id("scope", identity),
            workspace_identity=workspace_identity,
            selected_regions=tuple(selected_regions),
            discovery_boundary=discovery_boundary,
            inspection_boundary=inspection_boundary,
            semantic_disclosure_boundary=semantic_disclosure_boundary,
            modification_boundary=modification_boundary,
            exclusions=tuple(exclusions),
            project_trust=project_trust,
            platform_profile=platform_profile,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "workspace_identity": self.workspace_identity,
            "selected_regions": list(self.selected_regions),
            "discovery_boundary": self.discovery_boundary,
            "inspection_boundary": self.inspection_boundary,
            "semantic_disclosure_boundary": self.semantic_disclosure_boundary,
            "modification_boundary": self.modification_boundary,
            "exclusions": list(self.exclusions),
            "project_trust": self.project_trust,
            "platform_profile": self.platform_profile,
        }


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_type: str
    location: str
    status: str
    revision: str | None
    readability: str
    declared_scope: dict[str, Any]
    effective_scope: dict[str, Any]
    sensitivity: tuple[str, ...]
    provenance: dict[str, Any]
    status_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "type": self.source_type,
            "location": self.location,
            "status": self.status,
            "revision": self.revision,
            "readability": self.readability,
            "declared_scope": self.declared_scope,
            "effective_scope": self.effective_scope,
            "sensitivity": list(self.sensitivity),
            "provenance": self.provenance,
            "status_reason": self.status_reason,
        }


@dataclass(frozen=True)
class Claim:
    claim_id: str
    source_ref: str
    kind: str
    dimension: str
    modality: str
    normalized: str
    excerpt: str
    qualifiers: tuple[str, ...]
    span: dict[str, int]
    completeness: str = "complete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "source_ref": self.source_ref,
            "kind": self.kind,
            "dimension": self.dimension,
            "modality": self.modality,
            "normalized": self.normalized,
            "excerpt": self.excerpt,
            "qualifiers": list(self.qualifiers),
            "span": self.span,
            "completeness": self.completeness,
        }


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    producer: str
    summary: str
    source_refs: tuple[str, ...] = ()
    parent_evidence_refs: tuple[str, ...] = ()
    rule_or_provider: dict[str, Any] = field(default_factory=dict)
    disclosure: str = "location_only"
    location: str | None = None
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "producer": self.producer,
            "summary": self.summary,
            "source_refs": list(self.source_refs),
            "parent_evidence_refs": list(self.parent_evidence_refs),
            "rule_or_provider": self.rule_or_provider,
            "disclosure": self.disclosure,
            "location": self.location,
            "excerpt": self.excerpt,
        }
        return value


@dataclass(frozen=True)
class CheckExecution:
    execution_id: str
    check_id: str
    family: str
    question: str
    lifecycle: str
    state: str
    reason: dict[str, Any]
    evidence_refs: tuple[str, ...]
    completeness: str
    input_revisions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "check_id": self.check_id,
            "family": self.family,
            "question": self.question,
            "lifecycle": self.lifecycle,
            "state": self.state,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "completeness": self.completeness,
            "input_revisions": list(self.input_revisions),
        }


@dataclass(frozen=True)
class Assessment:
    label: str
    claim_refs: tuple[str, ...]
    region_ref: str
    dimension_ref: str
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "claim_refs": list(self.claim_refs),
            "region_ref": self.region_ref,
            "dimension_ref": self.dimension_ref,
            "status": self.status,
        }


@dataclass(frozen=True)
class ValidationQualifier:
    kind: str
    proposition: str
    confirm_condition: str
    refute_condition: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class InteractionCase:
    case_id: str
    check_ref: str
    question: str
    source_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    region_ref: str
    region: dict[str, Any]
    dimension_ref: str
    state: str
    assessments: tuple[Assessment, ...]
    validation_qualifiers: tuple[ValidationQualifier, ...]
    severity: str | None
    potential_severity: str | None
    confidence: str | None
    evidence_refs: tuple[str, ...]
    counterexample: dict[str, Any]
    next_action_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "check_ref": self.check_ref,
            "question": self.question,
            "source_refs": list(self.source_refs),
            "claim_refs": list(self.claim_refs),
            "region_ref": self.region_ref,
            "region": self.region,
            "dimension_ref": self.dimension_ref,
            "state": self.state,
            "assessments": [item.to_dict() for item in self.assessments],
            "validation_qualifiers": [item.to_dict() for item in self.validation_qualifiers],
            "severity": self.severity,
            "potential_severity": self.potential_severity,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "counterexample": self.counterexample,
            "next_action_refs": list(self.next_action_refs),
        }


@dataclass(frozen=True)
class FindingGroup:
    group_id: str
    member_case_refs: tuple[str, ...]
    grouping_rule: str
    relationship_summary: str
    relationship_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "member_case_refs": list(self.member_case_refs),
            "grouping_rule": self.grouping_rule,
            "relationship_summary": self.relationship_summary,
            "relationship_kind": self.relationship_kind,
        }


@dataclass(frozen=True)
class NextAction:
    action_id: str
    kind: str
    summary: str
    bounds: dict[str, Any]
    authority: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResultBuilder:
    scope: ScopePlan
    platform_profile: dict[str, Any]
    modes: dict[str, str]
    clock: Clock = field(default_factory=SystemClock)
    run_id: str = field(default_factory=lambda: f"run-{uuid4()}")
    started_at: datetime = field(init=False)
    sources: list[SourceRecord] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    checks: list[CheckExecution] = field(default_factory=list)
    cases: list[InteractionCase] = field(default_factory=list)
    groups: list[FindingGroup] = field(default_factory=list)
    next_actions: list[NextAction] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    semantic_calls: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.started_at = self.clock.now()

    def add_evidence(
        self,
        *,
        kind: str,
        producer: str,
        summary: str,
        source_refs: tuple[str, ...] = (),
        parent_evidence_refs: tuple[str, ...] = (),
        rule_or_provider: dict[str, Any] | None = None,
        disclosure: str = "location_only",
        location: str | None = None,
        excerpt: str | None = None,
    ) -> str:
        identity = {
            "kind": kind,
            "producer": producer,
            "summary": summary,
            "source_refs": source_refs,
            "parents": parent_evidence_refs,
            "rule_or_provider": rule_or_provider or {},
            "disclosure": disclosure,
            "location": location,
            "excerpt": excerpt,
        }
        evidence_id = stable_id("ev", identity)
        if evidence_id not in {item.evidence_id for item in self.evidence}:
            self.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    kind=kind,
                    producer=producer,
                    summary=summary,
                    source_refs=source_refs,
                    parent_evidence_refs=parent_evidence_refs,
                    rule_or_provider=rule_or_provider or {},
                    disclosure=disclosure,
                    location=location,
                    excerpt=excerpt,
                )
            )
        return evidence_id

    def add_check(
        self,
        *,
        check_id: str,
        family: str,
        question: str,
        state: str,
        reason: dict[str, Any],
        evidence_refs: tuple[str, ...] = (),
        completeness: str = "complete",
        input_revisions: tuple[str, ...] = (),
        lifecycle: str = "completed",
    ) -> str:
        identity = {
            "check_id": check_id,
            "question": question,
            "scope": self.scope.scope_id,
            "input_revisions": input_revisions,
            "rule_set": RULE_SET_VERSION,
        }
        execution_id = stable_id("check", identity)
        if any(item.execution_id == execution_id for item in self.checks):
            return execution_id
        self.checks.append(
            CheckExecution(
                execution_id=execution_id,
                check_id=check_id,
                family=family,
                question=question,
                lifecycle=lifecycle,
                state=state,
                reason=reason,
                evidence_refs=evidence_refs,
                completeness=completeness,
                input_revisions=input_revisions,
            )
        )
        return execution_id

    def add_case(
        self,
        *,
        check_ref: str,
        question: str,
        source_refs: tuple[str, ...],
        claim_refs: tuple[str, ...],
        region: dict[str, Any],
        dimension_ref: str,
        state: str,
        assessments: tuple[Assessment, ...] = (),
        qualifiers: tuple[ValidationQualifier, ...] = (),
        severity: str | None = None,
        potential_severity: str | None = None,
        confidence: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        counterexample: dict[str, Any] | None = None,
        next_action_refs: tuple[str, ...] = (),
    ) -> str:
        region_ref = stable_id("region", region)
        identity = {
            "check": next((item.check_id for item in self.checks if item.execution_id == check_ref), check_ref),
            "sources": sorted(source_refs),
            "claims": sorted(claim_refs),
            "region": region,
            "dimension": dimension_ref,
            "taxonomy": TAXONOMY_VERSION,
            "normalization": NORMALIZATION_VERSION,
        }
        case_id = stable_id("case", identity)
        existing_index = next((index for index, item in enumerate(self.cases) if item.case_id == case_id), None)
        if existing_index is not None:
            existing = self.cases[existing_index]
            merged_evidence = tuple(sorted(set(existing.evidence_refs) | set(evidence_refs)))
            merged_sources = tuple(sorted(set(existing.source_refs) | set(source_refs)))
            merged_claims = tuple(sorted(set(existing.claim_refs) | set(claim_refs)))
            self.cases[existing_index] = InteractionCase(
                case_id=existing.case_id,
                check_ref=existing.check_ref,
                question=existing.question,
                source_refs=merged_sources,
                claim_refs=merged_claims,
                region_ref=existing.region_ref,
                region=existing.region,
                dimension_ref=existing.dimension_ref,
                state=existing.state,
                assessments=existing.assessments,
                validation_qualifiers=existing.validation_qualifiers,
                severity=existing.severity,
                potential_severity=existing.potential_severity,
                confidence=existing.confidence,
                evidence_refs=merged_evidence,
                counterexample=existing.counterexample,
                next_action_refs=tuple(sorted(set(existing.next_action_refs) | set(next_action_refs))),
            )
            return case_id
        self.cases.append(
            InteractionCase(
                case_id=case_id,
                check_ref=check_ref,
                question=question,
                source_refs=source_refs,
                claim_refs=claim_refs,
                region_ref=region_ref,
                region=region,
                dimension_ref=dimension_ref,
                state=state,
                assessments=assessments,
                validation_qualifiers=qualifiers,
                severity=severity,
                potential_severity=potential_severity,
                confidence=confidence,
                evidence_refs=evidence_refs,
                counterexample=counterexample or {"considered": "none", "excluded": False},
                next_action_refs=next_action_refs,
            )
        )
        return case_id

    def add_next_action(self, *, kind: str, summary: str, bounds: dict[str, Any]) -> str:
        action_id = stable_id("action", {"kind": kind, "summary": summary, "bounds": bounds})
        if action_id not in {item.action_id for item in self.next_actions}:
            self.next_actions.append(NextAction(action_id, kind, summary, bounds))
        return action_id

    def to_unsealed_dict(self, outcome: str) -> dict[str, Any]:
        completed_at = self.clock.now()
        profile_ref = f"{self.platform_profile['profile_id']}@{self.platform_profile['profile_version']}"
        input_manifest = [
            {
                "source_id": item.source_id,
                "location": item.location,
                "status": item.status,
                "revision": item.revision,
            }
            for item in sorted(self.sources, key=lambda source: (source.location, source.source_id))
        ]
        checks = sorted(self.checks, key=lambda item: item.execution_id)
        coverage_by_family: list[dict[str, Any]] = []
        for family in sorted({item.family for item in checks}):
            family_checks = [item for item in checks if item.family == family]
            coverage_by_family.append(
                {
                    "family": family,
                    "attempted": sum(item.lifecycle != "not_started" for item in family_checks),
                    "completed": sum(item.lifecycle == "completed" for item in family_checks),
                    "not_run": sum(item.state == CheckState.NOT_RUN.value for item in family_checks),
                    "error": sum(item.state == CheckState.ERROR.value for item in family_checks),
                    "abstained": sum(item.state == CheckState.INSUFFICIENT_EVIDENCE.value for item in family_checks),
                }
            )
        gaps = [
            {
                "check_ref": item.execution_id,
                "state": item.state,
                "reason": item.reason,
            }
            for item in checks
            if item.state in {CheckState.NOT_RUN.value, CheckState.ERROR.value, CheckState.INSUFFICIENT_EVIDENCE.value}
        ]
        graph: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "sealed": False,
            "result_id": "pending",
            "run": {
                "run_id": self.run_id,
                "started_at": isoformat(self.started_at),
                "completed_at": isoformat(completed_at),
                "outcome": outcome,
                "product_version": __version__,
                "taxonomy_version": TAXONOMY_VERSION,
                "rule_set_version": RULE_SET_VERSION,
                "normalization_version": NORMALIZATION_VERSION,
                "grouping_version": GROUPING_VERSION,
                "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
                "platform_profiles": [profile_ref],
                "modes": self.modes,
            },
            "scope": self.scope.to_dict(),
            "inventory": {
                "sources": [item.to_dict() for item in sorted(self.sources, key=lambda source: (source.location, source.source_id))]
            },
            "claims": [item.to_dict() for item in sorted(self.claims, key=lambda claim: claim.claim_id)],
            "evidence": [item.to_dict() for item in sorted(self.evidence, key=lambda evidence: evidence.evidence_id)],
            "checks": [item.to_dict() for item in checks],
            "interaction_cases": [item.to_dict() for item in sorted(self.cases, key=lambda case: case.case_id)],
            "finding_groups": [item.to_dict() for item in sorted(self.groups, key=lambda group: group.group_id)],
            "coverage": {"by_family": coverage_by_family, "gaps": gaps},
            "next_actions": [item.to_dict() for item in sorted(self.next_actions, key=lambda action: action.action_id)],
            "diagnostics": sorted(self.diagnostics, key=lambda item: (item.get("code", ""), item.get("subject", ""))),
            "reproducibility": {
                "input_revision_manifest": digest(input_manifest),
                "configuration_digest": digest({"scope": self.scope.to_dict(), "modes": self.modes}),
                "semantic_calls": self.semantic_calls,
                "canonicalization": "agent-doctor-canonical-json/0.1+sha256",
            },
        }
        stable_graph: dict[str, Any] = dict(graph)
        stable_graph["run"] = {
            key: value
            for key, value in graph["run"].items()
            if key not in {"run_id", "started_at", "completed_at"}
        }
        stable_graph["result_id"] = "pending"
        graph["result_id"] = stable_id("result", stable_graph)
        return graph

    def seal(self, outcome: str | None = None) -> dict[str, Any]:
        from .schema import validate_result

        if outcome is None:
            has_error = any(item.state == CheckState.ERROR.value for item in self.checks)
            has_expected_gap = any(
                item.state in {CheckState.INSUFFICIENT_EVIDENCE.value, CheckState.NOT_RUN.value}
                and item.reason.get("expected", False)
                for item in self.checks
            )
            outcome = (
                RunOutcome.COMPLETE_WITH_GAPS.value
                if has_error or has_expected_gap
                else RunOutcome.COMPLETE.value
            )
        graph = self.to_unsealed_dict(outcome)
        errors = validate_result(graph, require_sealed=False)
        if errors:
            graph["run"]["outcome"] = RunOutcome.EXECUTION_FAILED.value
            graph["diagnostics"].extend(
                {"code": "result.invariant", "subject": error.path, "message": error.message}
                for error in errors
            )
            graph["sealed"] = False
            return graph
        graph["sealed"] = True
        return graph
