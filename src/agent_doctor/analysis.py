"""Offline deterministic Stage 03 pipeline and sealed-result orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .canonical import digest, stable_id
from .inventory import SourceCandidate, discover
from .model import (
    Assessment,
    FindingGroup,
    ResultBuilder,
    SystemClock,
    ValidationQualifier,
)
from .parser import ParsedSource, parse_source
from .privacy import SafeReader, minimize_excerpt, redact_secrets
from .profile import compatibility_decision, load_profile
from .resolution import (
    explicit_version_mismatch,
    extract_references,
    resolve_config_precedence,
    resolve_reference,
)
from .scope import ResolvedScope, ScopeOptions, plan_scope
from .types import CheckState, EvidenceKind, SourceStatus, SourceType
from .version import GROUPING_VERSION, NORMALIZATION_VERSION, RULE_SET_VERSION


@dataclass(frozen=True)
class AnalysisRequest:
    workspace: Path
    selected_path: Path | None = None
    include_user: bool = False
    include_system: bool = False
    project_trust: str = "unknown"
    semantic_mode: str = "disabled"
    profile_path: Path | None = None


@dataclass(frozen=True)
class AnalysisResponse:
    graph: dict[str, Any]
    scope: ResolvedScope


@dataclass
class _PipelineState:
    builder: ResultBuilder
    scope: ResolvedScope
    profile: dict[str, Any]
    candidates: list[SourceCandidate]
    snapshots: dict[str, str]
    parsed: dict[str, ParsedSource]
    source_evidence: dict[str, str]
    claim_evidence: dict[str, str]
    reader: SafeReader


def _region(scope: ResolvedScope, *, witness: str | None = None, state: str = "proven") -> dict[str, Any]:
    value: dict[str, Any] = {
        "paths": list(scope.plan.selected_regions),
        "intersection": state,
        "runtime_observed": False,
    }
    if witness:
        value["witness"] = witness
    return value


def _assessment(
    label: str,
    claim_refs: tuple[str, ...],
    region: dict[str, Any],
    dimension: str,
    *,
    status: str = "active",
) -> Assessment:
    return Assessment(label, claim_refs, stable_id("region", region), dimension, status)


def _source_revision_tuple(state: _PipelineState, source_refs: tuple[str, ...]) -> tuple[str, ...]:
    revisions = {
        item.source_id: item.revision
        for item in state.candidates
        if item.revision is not None
    }
    return tuple(sorted(revisions.get(source_ref, "unknown") for source_ref in source_refs))


def _add_case(
    state: _PipelineState,
    *,
    check_id: str,
    family: str,
    question: str,
    check_state: str,
    reason: dict[str, Any],
    source_refs: tuple[str, ...],
    claim_refs: tuple[str, ...] = (),
    region: dict[str, Any] | None = None,
    dimension: str,
    labels: tuple[str, ...] = (),
    assessments: tuple[Assessment, ...] | None = None,
    qualifiers: tuple[ValidationQualifier, ...] = (),
    severity: str | None = None,
    potential_severity: str | None = None,
    confidence: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    counterexample: dict[str, Any] | None = None,
    next_action_refs: tuple[str, ...] = (),
    completeness: str = "complete",
) -> str:
    effective_region = region or _region(state.scope)
    if assessments is None:
        assessments = tuple(
            _assessment(label, claim_refs, effective_region, dimension)
            for label in labels
        )
    check_ref = state.builder.add_check(
        check_id=check_id,
        family=family,
        question=question,
        state=check_state,
        reason=reason,
        evidence_refs=evidence_refs,
        completeness=completeness,
        input_revisions=_source_revision_tuple(state, source_refs),
    )
    return state.builder.add_case(
        check_ref=check_ref,
        question=question,
        source_refs=source_refs,
        claim_refs=claim_refs,
        region=effective_region,
        dimension_ref=dimension,
        state=check_state,
        assessments=assessments,
        qualifiers=qualifiers,
        severity=severity,
        potential_severity=potential_severity,
        confidence=confidence,
        evidence_refs=evidence_refs,
        counterexample=counterexample,
        next_action_refs=next_action_refs,
    )


def _replace_source_record(builder: ResultBuilder, candidate: SourceCandidate) -> None:
    for index, record in enumerate(builder.sources):
        if record.source_id == candidate.source_id:
            builder.sources[index] = candidate.to_record()
            return
    builder.sources.append(candidate.to_record())


def _read_and_parse(state: _PipelineState) -> None:
    updated: list[SourceCandidate] = []
    for candidate in state.candidates:
        current = candidate
        content: str | None = None
        if candidate.status == SourceStatus.DISCOVERED.value and candidate.path is not None and candidate.allowed_root is not None:
            result = state.reader.read_text(
                candidate.path,
                allowed_root=candidate.allowed_root,
                purpose="deterministic_analysis",
                source_type=candidate.source_type,
                inspection=candidate.inspection,
            )
            if result.status == "read":
                current = candidate.with_read(
                    status=SourceStatus.DISCOVERED.value,
                    revision=result.revision,
                    readability="readable",
                    sensitivity=result.sensitivity,
                    reason=candidate.status_reason,
                )
                content = result.content
            elif result.status == "partial":
                current = candidate.with_read(
                    status=SourceStatus.TRUNCATED.value,
                    revision=result.revision,
                    readability="partial",
                    sensitivity=result.sensitivity,
                    reason=result.diagnostic or "parser input was truncated",
                )
                content = result.content
            elif result.status == "missing":
                current = candidate.with_read(
                    status=SourceStatus.MISSING.value,
                    revision=None,
                    readability="missing",
                    sensitivity=(),
                    reason=result.diagnostic or "missing",
                )
            elif result.status in {"unreadable", "error"}:
                current = candidate.with_read(
                    status=SourceStatus.UNREADABLE.value,
                    revision=None,
                    readability=result.status,
                    sensitivity=(),
                    reason=result.diagnostic or "unreadable",
                )
            else:
                current = candidate.with_read(
                    status=SourceStatus.EXCLUDED.value,
                    revision=None,
                    readability=result.status,
                    sensitivity=result.sensitivity,
                    reason=result.diagnostic or "content withheld",
                )
        elif candidate.status == SourceStatus.SHADOWED.value:
            current = replace(candidate, readability="not_read")
        elif candidate.status in {SourceStatus.IGNORED.value, SourceStatus.EXCLUDED.value}:
            current = replace(candidate, readability="not_read")
        elif candidate.status == SourceStatus.MISSING.value:
            current = replace(candidate, readability="missing")

        updated.append(current)
        _replace_source_record(state.builder, current)
        source_evidence = state.builder.add_evidence(
            kind=EvidenceKind.OBSERVED.value,
            producer="inventory@0.1",
            summary=f"{current.location} is {current.status}: {current.status_reason}",
            source_refs=(current.source_id,),
            rule_or_provider={"profile": state.scope.plan.platform_profile},
            disclosure="location_only",
            location=current.location,
        )
        state.source_evidence[current.source_id] = source_evidence

        if current.status == SourceStatus.UNREADABLE.value and candidate.status == SourceStatus.DISCOVERED.value:
            _add_case(
                state,
                check_id="deterministic.source.readability",
                family="inventory",
                question=f"Could the inventoried source {current.location} be read for deterministic analysis?",
                check_state=CheckState.ERROR.value,
                reason={"code": "source_read_failed", "detail": current.status_reason, "expected": True},
                source_refs=(current.source_id,),
                dimension="source_readability",
                evidence_refs=(source_evidence,),
                counterexample={"considered": "The source was deliberately skipped.", "excluded": True, "basis": "The read attempt started and failed."},
                completeness="partial",
            )
        if content is None:
            continue
        state.snapshots[current.source_id] = content
        parsed = parse_source(current.source_id, current.source_type, content)
        state.parsed[current.source_id] = parsed
        for claim in parsed.claims:
            if claim.claim_id not in {item.claim_id for item in state.builder.claims}:
                state.builder.claims.append(claim)
            disclosure = "redacted" if "[REDACTED:" in claim.excerpt else "excerpt"
            evidence_id = state.builder.add_evidence(
                kind=EvidenceKind.OBSERVED.value,
                producer=f"parser@{NORMALIZATION_VERSION}",
                summary=f"Observed {claim.kind} claim at {current.location}:{claim.span['start_line']}",
                source_refs=(current.source_id,),
                rule_or_provider={"normalization_version": NORMALIZATION_VERSION},
                disclosure=disclosure,
                location=f"{current.location}:{claim.span['start_line']}",
                excerpt=claim.excerpt,
            )
            state.claim_evidence[claim.claim_id] = evidence_id
        for diagnostic in parsed.diagnostics:
            state.builder.diagnostics.append(
                {
                    "code": diagnostic.code,
                    "subject": current.location,
                    "message": diagnostic.message,
                    "line": diagnostic.line,
                    "severity": diagnostic.severity,
                }
            )
    state.candidates = updated

    inventory_evidence = tuple(sorted(state.source_evidence.values()))
    state.builder.add_check(
        check_id="deterministic.inventory.complete",
        family="inventory",
        question="Were all supported candidates in the frozen discovery scope retained in inventory?",
        state=CheckState.PASS.value,
        reason={"code": "inventory_retained", "source_count": len(state.candidates)},
        evidence_refs=inventory_evidence,
        input_revisions=tuple(sorted(item.revision or item.status for item in state.candidates)),
    )


def _metadata_checks(state: _PipelineState) -> None:
    profile_evidence = state.builder.add_evidence(
        kind=EvidenceKind.OBSERVED.value,
        producer="platform-profile-registry@0.1",
        summary="Reviewed Codex profile requires SKILL.md front matter with name and description.",
        rule_or_provider={
            "profile": state.scope.plan.platform_profile,
            "source": "https://learn.chatgpt.com/docs/build-skills",
        },
        disclosure="excerpt",
        excerpt="SKILL.md must include name and description.",
    )
    for candidate in state.candidates:
        if candidate.source_type not in {SourceType.SKILL_BODY.value, SourceType.SKILL_MANIFEST.value}:
            continue
        parsed = state.parsed.get(candidate.source_id)
        if parsed is None:
            continue
        metadata = parsed.metadata
        missing = [key for key in ("name", "description") if not isinstance(metadata.get(key), str) or not str(metadata.get(key)).strip()]
        invalid_diagnostics = [item for item in parsed.diagnostics if item.severity == "error"]
        if not missing and not invalid_diagnostics:
            state.builder.add_check(
                check_id="deterministic.skill.metadata",
                family="configuration",
                question=f"Does {candidate.location} contain the reviewed required metadata?",
                state=CheckState.PASS.value,
                reason={"code": "required_metadata_present"},
                evidence_refs=(state.source_evidence[candidate.source_id], profile_evidence),
                input_revisions=(candidate.revision or "unknown",),
            )
            continue
        detail = []
        if missing:
            detail.append(f"missing required field(s): {', '.join(missing)}")
        detail.extend(item.message for item in invalid_diagnostics)
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"configuration-rule-engine@{RULE_SET_VERSION}",
            summary=f"{candidate.location} has invalid required Skill metadata: {'; '.join(detail)}",
            source_refs=(candidate.source_id,),
            parent_evidence_refs=(state.source_evidence[candidate.source_id], profile_evidence),
            rule_or_provider={"rule_id": "codex.skill.required-metadata@0.1"},
            disclosure="location_only",
            location=candidate.location,
        )
        action = state.builder.add_next_action(
            kind="manual_repair",
            summary=f"Add or correct YAML front matter in {candidate.location}: name and description are required.",
            bounds={"target": candidate.location, "operation": "manual_edit", "automatic_apply": False},
        )
        _add_case(
            state,
            check_id="deterministic.skill.metadata",
            family="configuration",
            question=f"Is the required Skill metadata valid in {candidate.location}?",
            check_state=CheckState.FINDING.value,
            reason={"code": "invalid_required_metadata", "detail": detail},
            source_refs=(candidate.source_id,),
            claim_refs=tuple(item.claim_id for item in parsed.claims if item.kind == "trigger"),
            dimension="configuration",
            labels=("configuration_risk",),
            severity="medium",
            confidence="high",
            evidence_refs=(state.source_evidence[candidate.source_id], profile_evidence, derived),
            counterexample={
                "considered": "The metadata may be forward-compatible.",
                "excluded": True,
                "basis": "The cited current Skill contract makes name and description required; unrelated unknown fields were not rejected.",
            },
            next_action_refs=(action,),
        )

    for candidate in state.candidates:
        if candidate.source_type != SourceType.CONFIG.value:
            continue
        parsed = state.parsed.get(candidate.source_id)
        if not parsed:
            continue
        invalid = [item for item in parsed.diagnostics if item.code == "config.toml.invalid"]
        if not invalid:
            continue
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"configuration-rule-engine@{RULE_SET_VERSION}",
            summary=f"{candidate.location} is not valid TOML.",
            source_refs=(candidate.source_id,),
            parent_evidence_refs=(state.source_evidence[candidate.source_id],),
            rule_or_provider={"rule_id": "configuration.toml.syntax@0.1"},
            disclosure="location_only",
            location=candidate.location,
        )
        action = state.builder.add_next_action(
            kind="manual_repair",
            summary=f"Correct TOML syntax in {candidate.location}, then rerun Agent Doctor.",
            bounds={"target": candidate.location, "operation": "manual_edit", "automatic_apply": False},
        )
        _add_case(
            state,
            check_id="deterministic.configuration.syntax",
            family="configuration",
            question=f"Is {candidate.location} syntactically valid TOML?",
            check_state=CheckState.FINDING.value,
            reason={"code": "invalid_toml", "detail": invalid[0].message},
            source_refs=(candidate.source_id,),
            dimension="configuration",
            labels=("configuration_risk",),
            severity="medium",
            confidence="high",
            evidence_refs=(state.source_evidence[candidate.source_id], derived),
            counterexample={"considered": "The key may merely be unknown.", "excluded": True, "basis": "The document fails TOML syntax before field policy is considered."},
            next_action_refs=(action,),
            completeness="partial",
        )


def _duplicate_checks(state: _PipelineState) -> None:
    by_name: dict[str, list[tuple[SourceCandidate, ParsedSource, str]]] = {}
    for candidate in state.candidates:
        if candidate.source_type != SourceType.SKILL_BODY.value or candidate.status != SourceStatus.DISCOVERED.value:
            continue
        parsed = state.parsed.get(candidate.source_id)
        content = state.snapshots.get(candidate.source_id)
        if not parsed or content is None:
            continue
        name_value = parsed.metadata.get("name") or parsed.metadata.get("id")
        if not isinstance(name_value, str) or not name_value.strip():
            continue
        name_redaction = redact_secrets(name_value)
        if name_redaction.changed:
            state.builder.diagnostics.append(
                {
                    "code": "privacy.secret-bearing-identifier",
                    "subject": candidate.location,
                    "message": "A secret-like Skill identifier was excluded from duplicate-name comparison.",
                }
            )
            continue
        name_value = name_redaction.text
        normalized_content = re.sub(r"\s+", " ", redact_secrets(content).text).strip().casefold()
        by_name.setdefault(name_value.strip().casefold(), []).append((candidate, parsed, digest(normalized_content)))

    for name, entries in sorted(by_name.items()):
        if len(entries) < 2:
            continue
        source_refs = tuple(sorted(item[0].source_id for item in entries))
        claim_refs = tuple(
            sorted(
                claim.claim_id
                for _, parsed, _ in entries
                for claim in parsed.claims
                if claim.kind == "trigger"
            )
        )
        parent_evidence = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        identical = len({item[2] for item in entries}) == 1
        if identical:
            derived = state.builder.add_evidence(
                kind=EvidenceKind.DERIVED.value,
                producer=f"duplicate-rule-engine@{RULE_SET_VERSION}",
                summary=f"{len(entries)} discovered Skill installations share name {name!r} and normalized content.",
                source_refs=source_refs,
                parent_evidence_refs=parent_evidence,
                rule_or_provider={"rule_id": "codex.skill.structural-duplicate@0.1"},
                disclosure="location_only",
            )
            action = state.builder.add_next_action(
                kind="manual_repair",
                summary=f"Review the duplicate {name!r} installations and manually retain only the intended occurrence.",
                bounds={"targets": [item[0].location for item in entries], "operation": "manual_remove_or_disable", "automatic_apply": False},
            )
            _add_case(
                state,
                check_id="deterministic.skill.duplicate-installation",
                family="duplicates",
                question=f"Do the discovered installations named {name!r} add materially distinct behavior?",
                check_state=CheckState.FINDING.value,
                reason={"code": "structural_duplicate", "occurrences": len(entries)},
                source_refs=source_refs,
                claim_refs=claim_refs,
                dimension="trigger",
                labels=("scope_overlap", "behavioral_redundancy"),
                severity="medium",
                confidence="high",
                evidence_refs=parent_evidence + (derived,),
                counterexample={"considered": "The same name may identify distinct behavior.", "excluded": True, "basis": "Normalized content is identical across all discovered occurrences."},
                next_action_refs=(action,),
            )
        else:
            # The reviewed profile establishes only that duplicate names can
            # both be listed.  Divergent bodies do not prove selection,
            # ambiguity, or causality, and semantic analysis is deliberately
            # outside the product slice.  Preserve the occurrence and expose
            # the skipped question without manufacturing an inference.
            _add_case(
                state,
                check_id="semantic.skill.duplicate-name-selection-risk",
                family="semantic",
                question=f"Do divergent same-name Skills {name!r} create a selection risk?",
                check_state=CheckState.NOT_RUN.value,
                reason={"code": "semantic_mode_disabled", "runtime_selection_unobserved": True, "expected": False},
                source_refs=source_refs,
                claim_refs=claim_refs,
                dimension="trigger",
                evidence_refs=parent_evidence,
                counterexample={"considered": "Both entries may be intentionally exposed for explicit invocation.", "excluded": False, "basis": "The profile says both may appear and provides no deterministic selection outcome."},
            )


def _add_resource_record(
    state: _PipelineState,
    *,
    declaration_source: SourceCandidate,
    target: Path,
    display: str,
    status: str,
    reason: str,
    revision: str | None = None,
    sensitivity: tuple[str, ...] = (),
) -> SourceCandidate:
    existing = next(
        (
            item
            for item in state.candidates
            if item.source_type == SourceType.RESOURCE.value
            and item.path is not None
            and item.path.resolve(strict=False) == target.resolve(strict=False)
        ),
        None,
    )
    if existing:
        return existing
    safe_display = display
    if any(
        item.location == safe_display and item.source_type == SourceType.RESOURCE.value
        for item in state.candidates
    ):
        occurrence = 2 + sum(
            item.location.startswith(safe_display + "#redacted-occurrence-")
            for item in state.candidates
            if item.source_type == SourceType.RESOURCE.value
        )
        safe_display = f"{safe_display}#redacted-occurrence-{occurrence:04d}"
    resource = SourceCandidate(
        source_id=stable_id("source", {"type": SourceType.RESOURCE.value, "location": safe_display}),
        path=target,
        source_type=SourceType.RESOURCE.value,
        location=safe_display,
        status=status,
        status_reason=reason,
        allowed_root=declaration_source.allowed_root,
        inspection="allowed",
        semantic_disclosure="withheld",
        effective_scope={"state": "referenced_only", "declared_by": declaration_source.source_id},
        revision=revision,
        readability="readable" if status == SourceStatus.DISCOVERED.value else status,
        sensitivity=sensitivity,
        provenance={"declared_by": declaration_source.source_id},
    )
    state.candidates.append(resource)
    _replace_source_record(state.builder, resource)
    evidence = state.builder.add_evidence(
        kind=EvidenceKind.OBSERVED.value,
        producer="reference-inventory@0.1",
        summary=f"Referenced resource {safe_display} is {status}: {reason}",
        source_refs=(resource.source_id,),
        disclosure="location_only",
        location=safe_display,
    )
    state.source_evidence[resource.source_id] = evidence
    return resource


def _reference_checks(state: _PipelineState) -> None:
    for candidate in list(state.candidates):
        if candidate.source_type not in {SourceType.SKILL_BODY.value, SourceType.INSTRUCTION.value, SourceType.OVERRIDE.value}:
            continue
        content = state.snapshots.get(candidate.source_id)
        if content is None or candidate.path is None or candidate.allowed_root is None:
            continue
        for declaration in extract_references(candidate.source_id, content):
            safe_declaration = minimize_excerpt(declaration.raw, limit=240)[0]
            resolution = resolve_reference(
                declaration,
                declaring_path=candidate.path,
                allowed_root=candidate.allowed_root,
                display_root=state.scope.workspace,
                variables={},
            )
            declaration_evidence = state.builder.add_evidence(
                kind=EvidenceKind.OBSERVED.value,
                producer="reference-parser@0.1",
                summary=f"Observed reference declaration at {candidate.location}:{declaration.line}",
                source_refs=(candidate.source_id,),
                rule_or_provider={"resolver_profile": state.scope.plan.platform_profile},
                disclosure="excerpt",
                location=f"{candidate.location}:{declaration.line}",
                excerpt=minimize_excerpt(declaration.raw)[0],
            )
            resolution_evidence = state.builder.add_evidence(
                kind=EvidenceKind.DERIVED.value,
                producer=f"reference-resolver@{RULE_SET_VERSION}",
                summary=f"Reference {safe_declaration!r} resolved with status {resolution.status}: {resolution.reason}",
                source_refs=(candidate.source_id,),
                parent_evidence_refs=(declaration_evidence,),
                rule_or_provider={"rule_id": "codex.reference.declaring-source-relative@0.1"},
                disclosure="location_only",
                location=f"{candidate.location}:{declaration.line}",
            )
            question = f"Is the reference {safe_declaration!r} at {candidate.location}:{declaration.line} valid inside its frozen scope?"
            if resolution.status in {"missing", "unreadable", "unsupported_type"} and resolution.target_path is not None and resolution.normalized_target:
                resource_status = SourceStatus.MISSING.value if resolution.status == "missing" else SourceStatus.UNREADABLE.value
                _add_resource_record(
                    state,
                    declaration_source=candidate,
                    target=resolution.target_path,
                    display=resolution.normalized_target,
                    status=resource_status,
                    reason=resolution.reason,
                )
            if resolution.status in {"missing", "escape", "unreadable", "unsupported_type"}:
                action = state.builder.add_next_action(
                    kind="manual_repair",
                    summary=f"Correct or remove the reference {safe_declaration!r} in {candidate.location}; no outside target was read.",
                    bounds={"target": candidate.location, "reference": safe_declaration, "operation": "manual_edit", "automatic_apply": False},
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    check_state=CheckState.FINDING.value,
                    reason={"code": f"reference_{resolution.status}", "detail": resolution.reason, "outside_read_attempted": False},
                    source_refs=(candidate.source_id,),
                    dimension="reference_validity",
                    labels=("invalid_reference",),
                    severity="medium",
                    confidence="high",
                    evidence_refs=(declaration_evidence, resolution_evidence),
                    counterexample={"considered": "The target may exist outside the scan or be optional.", "excluded": declaration.required or resolution.status == "escape", "basis": "The supported resolver and frozen package boundary decide validity without reading outside content."},
                    next_action_refs=(action,),
                )
                continue
            if resolution.status == "unsupported":
                action = state.builder.add_next_action(
                    kind="evidence_request",
                    summary="Select a reviewed platform profile that explicitly supports this reference variable or rewrite it as a supported relative reference.",
                    bounds={"source": candidate.location, "reference": safe_declaration},
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
                    reason={"code": "unsupported_reference_form", "missing_evidence": resolution.reason, "expected": True},
                    source_refs=(candidate.source_id,),
                    dimension="reference_validity",
                    confidence="high",
                    evidence_refs=(declaration_evidence, resolution_evidence),
                    counterexample={"considered": "The variable may be supported by another platform version.", "excluded": False, "basis": "The selected profile does not establish it."},
                    next_action_refs=(action,),
                )
                continue
            if resolution.status == "error":
                _add_case(
                    state,
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    check_state=CheckState.ERROR.value,
                    reason={"code": "reference_resolution_error", "detail": resolution.reason, "expected": True},
                    source_refs=(candidate.source_id,),
                    dimension="reference_validity",
                    evidence_refs=(declaration_evidence, resolution_evidence),
                    counterexample={"considered": "The reference is invalid.", "excluded": False, "basis": "Execution failed before validity was determined."},
                    completeness="partial",
                )
                continue

            assert resolution.target_path is not None and resolution.normalized_target is not None
            target_read = state.reader.read_text(
                resolution.target_path,
                allowed_root=candidate.allowed_root,
                purpose="reference_compatibility",
                source_type=SourceType.RESOURCE.value,
                inspection="allowed",
            )
            if target_read.status in {"unreadable", "error", "missing", "denied", "withheld"}:
                resource_status = (
                    SourceStatus.MISSING.value
                    if target_read.status == "missing"
                    else SourceStatus.EXCLUDED.value
                    if target_read.status in {"denied", "withheld"}
                    else SourceStatus.UNREADABLE.value
                )
                resource = _add_resource_record(
                    state,
                    declaration_source=candidate,
                    target=resolution.target_path,
                    display=resolution.normalized_target,
                    status=resource_status,
                    reason=target_read.diagnostic or f"reference target read ended as {target_read.status}",
                    revision=target_read.revision,
                    sensitivity=target_read.sensitivity,
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    check_state=CheckState.ERROR.value,
                    reason={"code": "reference_target_read_error", "detail": target_read.diagnostic, "expected": True},
                    source_refs=(candidate.source_id, resource.source_id),
                    dimension="reference_validity",
                    evidence_refs=(declaration_evidence, resolution_evidence, state.source_evidence[resource.source_id]),
                    counterexample={"considered": "The declaration may be invalid.", "excluded": False, "basis": "The target read failed after the check started, so validity was not adjudicated."},
                    completeness="partial",
                )
                continue
            resource = _add_resource_record(
                state,
                declaration_source=candidate,
                target=resolution.target_path,
                display=resolution.normalized_target,
                status=SourceStatus.TRUNCATED.value if target_read.status == "partial" else SourceStatus.DISCOVERED.value,
                reason=(
                    target_read.diagnostic or "reference target was truncated"
                    if target_read.status == "partial"
                    else "supported reference resolved inside scope"
                ),
                revision=target_read.revision,
                sensitivity=target_read.sensitivity,
            )
            state.builder.add_check(
                check_id="deterministic.reference.validity",
                family="references",
                question=question,
                state=CheckState.PASS.value,
                reason={"code": "reference_valid"},
                evidence_refs=(declaration_evidence, resolution_evidence, state.source_evidence[resource.source_id]),
                input_revisions=tuple(filter(None, (candidate.revision, target_read.revision))),
            )
            if target_read.content is None:
                continue
            if target_read.status == "partial":
                action = state.builder.add_next_action(
                    kind="evidence_request",
                    summary=f"Rerun with a reviewed parser bound sufficient to inspect {resolution.normalized_target} completely.",
                    bounds={"target": resolution.normalized_target, "outside_scope": False},
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.compatibility",
                    family="references",
                    question=f"Is {resolution.normalized_target} completely available for compatibility analysis?",
                    check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
                    reason={"code": "reference_target_truncated", "expected": True},
                    source_refs=(candidate.source_id, resource.source_id),
                    dimension="reference_compatibility",
                    confidence="high",
                    evidence_refs=(declaration_evidence, state.source_evidence[resource.source_id]),
                    counterexample={"considered": "The decisive compatibility declaration may occur after the parser bound.", "excluded": False, "basis": "The target snapshot is partial."},
                    next_action_refs=(action,),
                    completeness="partial",
                )
                continue
            mismatch, mismatch_reason = explicit_version_mismatch(content, target_read.content)
            if mismatch:
                compatibility_evidence = state.builder.add_evidence(
                    kind=EvidenceKind.DERIVED.value,
                    producer=f"reference-compatibility@{RULE_SET_VERSION}",
                    summary=mismatch_reason or "explicit reference compatibility mismatch",
                    source_refs=(candidate.source_id, resource.source_id),
                    parent_evidence_refs=(declaration_evidence, state.source_evidence[resource.source_id]),
                    rule_or_provider={"rule_id": "reference.explicit-version-incompatibility@0.1"},
                    disclosure="location_only",
                )
                action = state.builder.add_next_action(
                    kind="manual_repair",
                    summary=f"Replace {resolution.normalized_target} with a target explicitly compatible with the required schema.",
                    bounds={"target": candidate.location, "operation": "manual_reference_update", "automatic_apply": False},
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.compatibility",
                    family="references",
                    question=f"Is {resolution.normalized_target} compatible with its declared consumer?",
                    check_state=CheckState.FINDING.value,
                    reason={"code": "explicit_version_incompatibility", "detail": mismatch_reason},
                    source_refs=(candidate.source_id, resource.source_id),
                    dimension="reference_compatibility",
                    labels=("stale_reference",),
                    severity="high",
                    confidence="high",
                    evidence_refs=(declaration_evidence, state.source_evidence[resource.source_id], compatibility_evidence),
                    counterexample={"considered": "An older target may be intentionally pinned.", "excluded": True, "basis": "The target explicitly declares incompatibility with the required schema."},
                    next_action_refs=(action,),
                )


def _configuration_precedence_checks(state: _PipelineState) -> dict[str, Any]:
    parsed_configs = [
        (candidate, state.parsed[candidate.source_id])
        for candidate in state.candidates
        if candidate.source_type == SourceType.CONFIG.value and candidate.source_id in state.parsed
    ]
    winners, all_values, unknown_keys = resolve_config_precedence(parsed_configs)
    profile_evidence = state.builder.add_evidence(
        kind=EvidenceKind.OBSERVED.value,
        producer="platform-profile-registry@0.1",
        summary="Reviewed Codex configuration precedence is CLI, trusted project closest, profile, user, system, built-in.",
        rule_or_provider={"profile": state.scope.plan.platform_profile, "source": "https://learn.chatgpt.com/docs/config-file/config-basic"},
        disclosure="excerpt",
        excerpt="CLI > trusted project closest > profile > user > system > built-in",
    )
    for key in unknown_keys:
        source_refs = tuple(sorted(item.source_ref for item in all_values[key]))
        parents = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"precedence-resolver@{RULE_SET_VERSION}",
            summary=f"Effective value for {key} is unknown because project trust is unknown.",
            source_refs=source_refs,
            parent_evidence_refs=parents + (profile_evidence,),
            rule_or_provider={"rule_id": "codex.config.trust-gated-precedence@0.1"},
            disclosure="location_only",
        )
        action = state.builder.add_next_action(
            kind="evidence_request",
            summary="Rerun with --project-trust trusted or --project-trust untrusted after verifying Codex trust state.",
            bounds={"key": key, "accepted_values": ["trusted", "untrusted"]},
        )
        _add_case(
            state,
            check_id="deterministic.configuration.precedence",
            family="precedence",
            question=f"Which configuration value governs {key}?",
            check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
            reason={"code": "project_trust_unknown", "missing_evidence": "Codex project trust state", "expected": True},
            source_refs=source_refs,
            dimension=f"configuration:{key}",
            confidence="high",
            evidence_refs=parents + (profile_evidence, derived),
            counterexample={"considered": "The closest project file wins.", "excluded": False, "basis": "Project layers are skipped when untrusted, and trust was not supplied."},
            next_action_refs=(action,),
        )
    for key, values in all_values.items():
        effective_values = [item for item in values if item.applicability == "applicable"]
        if len(effective_values) < 2 or key not in winners:
            continue
        source_refs = tuple(sorted(item.source_ref for item in effective_values))
        claim_refs = tuple(
            sorted(
                claim.claim_id
                for source_ref in source_refs
                for claim in state.parsed[source_ref].claims
                if claim.dimension == f"configuration:{key}"
            )
        )
        parents = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        winner = winners[key]
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"precedence-resolver@{RULE_SET_VERSION}",
            summary=f"Configuration key {key} is governed by {winner.source_ref} under the reviewed layer order.",
            source_refs=source_refs,
            parent_evidence_refs=parents + (profile_evidence,),
            rule_or_provider={"rule_id": "codex.config.layer-precedence@0.1"},
            disclosure="location_only",
        )
        region = _region(state.scope)
        _add_case(
            state,
            check_id="deterministic.configuration.precedence",
            family="precedence",
            question=f"Which effective source governs configuration key {key}?",
            check_state=CheckState.PASS.value,
            reason={"code": "precedence_resolved", "winner_source_ref": winner.source_ref},
            source_refs=source_refs,
            claim_refs=claim_refs,
            region=region,
            dimension=f"configuration:{key}",
            labels=("precedence_override",),
            severity="info",
            confidence="high",
            evidence_refs=parents + (profile_evidence, derived),
            counterexample={"considered": "All layer values remain equally effective.", "excluded": True, "basis": "The compatible reviewed profile defines the winner."},
        )
    return {key: item.value for key, item in winners.items()}


def _instruction_budget_check(state: _PipelineState, effective_config: dict[str, Any]) -> None:
    active = [
        item
        for item in state.candidates
        if item.source_type in {SourceType.INSTRUCTION.value, SourceType.OVERRIDE.value}
        and item.status == SourceStatus.DISCOVERED.value
        and item.path is not None
        and item.allowed_root == state.scope.workspace
        and item.source_id in state.snapshots
    ]
    if not active:
        return
    configured_limit = effective_config.get("project_doc_max_bytes")
    if configured_limit is None:
        configured_limit = state.profile["rules"]["instructions"]["project"]["default_max_bytes"]
    if not isinstance(configured_limit, int) or configured_limit <= 0:
        return
    total = sum(len(state.snapshots[item.source_id].encode("utf-8")) for item in active)
    parents = tuple(state.source_evidence[item.source_id] for item in active)
    profile_ev = state.builder.add_evidence(
        kind=EvidenceKind.OBSERVED.value,
        producer="platform-profile-registry@0.1",
        summary=f"Reviewed project instruction limit is {configured_limit} bytes for this configuration.",
        rule_or_provider={"profile": state.scope.plan.platform_profile, "rule_id": "codex.instructions.project_doc_max_bytes@0.1"},
        disclosure="location_only",
    )
    derived = state.builder.add_evidence(
        kind=EvidenceKind.DERIVED.value,
        producer=f"budget-rule-engine@{RULE_SET_VERSION}",
        summary=f"Applicable project instruction bytes measured {total} against limit {configured_limit}.",
        source_refs=tuple(item.source_id for item in active),
        parent_evidence_refs=parents + (profile_ev,),
        rule_or_provider={"rule_id": "codex.instructions.project-byte-budget@0.1", "unit": "bytes", "phase": "project_instruction_chain"},
        disclosure="location_only",
    )
    if total <= configured_limit:
        state.builder.add_check(
            check_id="deterministic.context.instruction-budget",
            family="context_budget",
            question="Does the applicable project instruction chain exceed its reviewed byte limit?",
            state=CheckState.PASS.value,
            reason={"code": "within_budget", "measured": total, "limit": configured_limit, "unit": "bytes"},
            evidence_refs=parents + (profile_ev, derived),
            input_revisions=tuple(item.revision or "unknown" for item in active),
        )
        return
    action = state.builder.add_next_action(
        kind="manual_repair",
        summary="Reduce or split applicable project instructions while preserving directory-specific qualifiers; rerun to verify the measured byte chain.",
        bounds={"targets": [item.location for item in active], "operation": "manual_edit", "automatic_apply": False},
    )
    _add_case(
        state,
        check_id="deterministic.context.instruction-budget",
        family="context_budget",
        question="Does the applicable project instruction chain exceed its reviewed byte limit?",
        check_state=CheckState.FINDING.value,
        reason={"code": "documented_budget_exceeded", "measured": total, "limit": configured_limit, "unit": "bytes"},
        source_refs=tuple(item.source_id for item in active),
        dimension="context_use",
        labels=("context_budget_risk",),
        severity="medium",
        confidence="high",
        evidence_refs=parents + (profile_ev, derived),
        counterexample={"considered": "The files only look long and may not all load.", "excluded": True, "basis": "The full applicable chain and the compatible byte limit were measured in the documented loading phase."},
        next_action_refs=(action,),
    )


def _skill_budget_abstention(state: _PipelineState) -> None:
    skills = [
        item
        for item in state.candidates
        if item.source_type == SourceType.SKILL_BODY.value
        and item.status == SourceStatus.DISCOVERED.value
        and item.source_id in state.parsed
    ]
    if not skills:
        return
    minimum_chars = 0
    for item in skills:
        metadata = state.parsed[item.source_id].metadata
        minimum_chars += len(str(metadata.get("name", ""))) + len(str(metadata.get("description", ""))) + len(item.location)
    budget_rule = state.profile["rules"]["skills"]["initial_list"]
    if minimum_chars <= int(budget_rule["unknown_context_character_budget"]):
        return
    parents = tuple(state.source_evidence[item.source_id] for item in skills)
    derived = state.builder.add_evidence(
        kind=EvidenceKind.DERIVED.value,
        producer=f"budget-rule-engine@{RULE_SET_VERSION}",
        summary=f"Skill-list field content has a {minimum_chars}-character lower bound, but exact active context allocation and serialization are unavailable.",
        source_refs=tuple(item.source_id for item in skills),
        parent_evidence_refs=parents,
        rule_or_provider={"rule_id": "codex.skills.initial-list-budget-observation@0.1", "profile": state.scope.plan.platform_profile},
        disclosure="location_only",
    )
    action = state.builder.add_next_action(
        kind="evidence_request",
        summary="Capture the actual Codex initial skill-list warning/omission state and active model context before asserting truncation.",
        bounds={"content": "generated skill-list metadata only", "runtime_causality": False},
    )
    _add_case(
        state,
        check_id="deterministic.context.skill-list-budget",
        family="context_budget",
        question="Does the discovered Skill list deterministically omit or truncate a Skill?",
        check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
        reason={"code": "exact_allocation_or_serialization_unknown", "measured_lower_bound": minimum_chars, "expected": True},
        source_refs=tuple(item.source_id for item in skills),
        dimension="context_use",
        confidence="high",
        evidence_refs=parents + (derived,),
        counterexample={"considered": "A known model context may allocate more than the fallback and Codex may only shorten descriptions.", "excluded": False, "basis": "No generated list or active context allocation was observed."},
        next_action_refs=(action,),
    )


def _semantic_coverage(state: _PipelineState) -> None:
    mode_evidence = state.builder.add_evidence(
        kind=EvidenceKind.OBSERVED.value,
        producer="session-coordinator@0.1",
        summary=f"Semantic analysis mode is {state.builder.modes['semantic']}.",
        rule_or_provider={"mode": state.builder.modes["semantic"]},
        disclosure="location_only",
    )
    if state.builder.modes["semantic"] == "disabled":
        _add_case(
            state,
            check_id="semantic.skill.relationship",
            family="semantic",
            question="Were open-ended semantic Skill relationship checks attempted?",
            check_state=CheckState.NOT_RUN.value,
            reason={"code": "semantic_mode_disabled", "expected": False},
            source_refs=(),
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence,),
            counterexample={"considered": "No relationship was found.", "excluded": True, "basis": "The check never started."},
        )


def _group_cases(state: _PipelineState) -> None:
    grouped: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for case in state.builder.cases:
        if case.state not in {CheckState.FINDING.value, CheckState.CANDIDATE.value}:
            continue
        key = (tuple(sorted(case.source_refs)), case.region_ref)
        grouped.setdefault(key, []).append(case.case_id)
    for (source_refs, region_ref), members in sorted(grouped.items()):
        member_cases = [case for case in state.builder.cases if case.case_id in members]
        dimensions = sorted({case.dimension_ref for case in member_cases})
        labels = sorted({assessment.label for case in member_cases for assessment in case.assessments})
        identity = {
            "members": sorted(members),
            "grouping_version": GROUPING_VERSION,
            "sources": source_refs,
            "region": region_ref,
        }
        state.builder.groups.append(
            FindingGroup(
                group_id=stable_id("group", identity),
                member_case_refs=tuple(sorted(members)),
                grouping_rule=GROUPING_VERSION,
                relationship_summary=(
                    f"{len(members)} case(s) across {len(dimensions)} dimension(s); labels: {', '.join(labels) or 'none'}. "
                    "Static evidence does not assert runtime selection or causality."
                ),
                relationship_kind="dimension_specific" if len(dimensions) > 1 else "same_interaction",
            )
        )


def analyze(request: AnalysisRequest, *, clock: Any | None = None, run_id: str | None = None) -> AnalysisResponse:
    profile = load_profile(request.profile_path)
    compatibility = compatibility_decision(profile)
    scope = plan_scope(
        ScopeOptions(
            workspace=request.workspace,
            selected_path=request.selected_path,
            include_user=request.include_user,
            include_system=request.include_system,
            project_trust=request.project_trust,
            semantic_mode=request.semantic_mode,
        ),
        profile,
    )
    builder_kwargs: dict[str, Any] = {
        "scope": scope.plan,
        "platform_profile": profile,
        "modes": {
            "deterministic": "enabled",
            "semantic": request.semantic_mode,
            "repair": "proposal_only",
        },
        "clock": clock or SystemClock(),
    }
    if run_id is not None:
        builder_kwargs["run_id"] = run_id
    builder = ResultBuilder(**builder_kwargs)
    state = _PipelineState(builder, scope, profile, [], {}, {}, {}, {}, SafeReader())
    if not compatibility.usable:
        builder.diagnostics.append({"code": "profile.unusable", "subject": scope.plan.platform_profile, "message": compatibility.reason})
        check_state = CheckState.ERROR.value if compatibility.state == "error" else CheckState.INSUFFICIENT_EVIDENCE.value
        _add_case(
            state,
            check_id="deterministic.platform-profile.compatibility",
            family="compatibility",
            question="Can the selected profile support version-dependent deterministic conclusions?",
            check_state=check_state,
            reason={"code": "profile_unusable", "detail": compatibility.reason, "expected": True},
            source_refs=(),
            dimension="platform_compatibility",
            confidence="high" if check_state == CheckState.INSUFFICIENT_EVIDENCE.value else None,
            evidence_refs=(),
            counterexample={"considered": "The profile may still describe the current platform.", "excluded": False, "basis": "Compatibility was not established."},
        )
        return AnalysisResponse(builder.seal("execution_failed" if check_state == CheckState.ERROR.value else "complete_with_gaps"), scope)

    state.candidates = discover(scope, profile)
    _read_and_parse(state)
    _metadata_checks(state)
    _duplicate_checks(state)
    _reference_checks(state)
    effective_config = _configuration_precedence_checks(state)
    _instruction_budget_check(state, effective_config)
    _skill_budget_abstention(state)
    _semantic_coverage(state)
    _group_cases(state)
    graph = builder.seal()
    return AnalysisResponse(graph, scope)
