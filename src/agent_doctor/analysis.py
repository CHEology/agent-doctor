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
    explicit_version_compatibility,
    extract_references,
    resolve_config_precedence,
    resolve_reference,
)
from .scope import ResolvedScope, ScopeOptions, plan_scope
from .semantic_panel import adjudicate_panel_answers, recommendation_is_compatible
from .semantic_workflow import (
    response_digest as semantic_response_digest,
    validate_manifest_against_graph,
    validate_manifest_digest,
    validate_provider_response,
)
from .types import CheckState, EvidenceKind, SourceStatus, SourceType
from .version import GROUPING_VERSION, NORMALIZATION_VERSION, RULE_SET_VERSION


@dataclass(frozen=True)
class AnalysisRequest:
    workspace: Path
    selected_path: Path | None = None
    include_user: bool = False
    include_system: bool = False
    project_trust: str = "unknown"
    semantic_mode: str = "enabled"
    profile_path: Path | None = None
    semantic_manifest: dict[str, Any] | None = None
    semantic_invocation: dict[str, Any] | None = None
    semantic_response: dict[str, Any] | None = None
    semantic_consent_digest: str | None = None
    semantic_not_applicable_reason: str | None = None
    semantic_not_applicable_source_refs: tuple[str, ...] = ()


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

        if current.status == SourceStatus.UNREADABLE.value and candidate.status in {
            SourceStatus.DISCOVERED.value,
            SourceStatus.UNREADABLE.value,
        }:
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
    coverage_gaps = [
        item
        for item in state.candidates
        if bool((item.provenance or {}).get("coverage_gap"))
    ]
    if coverage_gaps:
        source_refs = tuple(sorted(item.source_id for item in coverage_gaps))
        evidence_refs = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        has_unreadable = any(item.status == SourceStatus.UNREADABLE.value for item in coverage_gaps)
        _add_case(
            state,
            check_id="deterministic.inventory.complete",
            family="inventory",
            question="Were all supported candidates in the frozen discovery scope retained in inventory?",
            check_state=CheckState.ERROR.value if has_unreadable else CheckState.INSUFFICIENT_EVIDENCE.value,
            reason={
                "code": "inventory_coverage_gap",
                "gap_count": len(coverage_gaps),
                "statuses": sorted({item.status for item in coverage_gaps}),
                "expected": True,
            },
            source_refs=source_refs,
            dimension="inventory_coverage",
            confidence=None if has_unreadable else "high",
            evidence_refs=evidence_refs,
            counterexample={
                "considered": "The omitted portion may contain no additional Skills.",
                "excluded": False,
                "basis": "The bounded discovery operation could not establish that proposition.",
            },
            completeness="partial",
        )
    else:
        state.builder.add_check(
            check_id="deterministic.inventory.complete",
            family="inventory",
            question="Were all supported candidates in the frozen discovery scope retained in inventory?",
            state=CheckState.PASS.value,
            reason={"code": "inventory_retained", "source_count": len(state.candidates)},
            evidence_refs=inventory_evidence,
            input_revisions=tuple(sorted(item.revision or item.status for item in state.candidates)),
        )


def _local_observed_applicability_checks(state: _PipelineState) -> None:
    """Keep local cache/store presence separate from runtime activation."""

    grouped: dict[str, list[SourceCandidate]] = {}
    for candidate in state.candidates:
        if candidate.source_type != SourceType.SKILL_BODY.value or candidate.status != SourceStatus.DISCOVERED.value:
            continue
        if (candidate.effective_scope or {}).get("state") != "unknown":
            continue
        if (candidate.provenance or {}).get("inventory_basis") != "local_filesystem_observation":
            continue
        scope_kind = str((candidate.effective_scope or {}).get("scope_kind", "local_observed_skill"))
        grouped.setdefault(scope_kind, []).append(candidate)

    for scope_kind, candidates in sorted(grouped.items()):
        source_refs = tuple(sorted(item.source_id for item in candidates))
        evidence_refs = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        action = state.builder.add_next_action(
            kind="evidence_request",
            summary=(
                f"Compare the {len(candidates)} locally observed {scope_kind} Skill artifacts with an active "
                "Codex skill catalogue before treating them as runtime-selected."
            ),
            bounds={
                "source_refs": list(source_refs),
                "operation": "manual_catalogue_comparison",
                "runtime_causality": False,
                "automatic_apply": False,
            },
        )
        _add_case(
            state,
            check_id="deterministic.skill.local-observed-applicability",
            family="applicability",
            question=f"Are the {scope_kind} Skill artifacts active in the current Codex runtime?",
            check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
            reason={
                "code": "local_inventory_does_not_prove_runtime_activation",
                "observed_count": len(candidates),
                "runtime_selection_observed": False,
                "expected": True,
            },
            source_refs=source_refs,
            region={
                "paths": ["observed-scope://" + re.sub(r"[^a-z0-9]+", "-", scope_kind.casefold()).strip("-")],
                "intersection": "unknown",
                "runtime_observed": False,
            },
            dimension="applicability",
            confidence="high",
            evidence_refs=evidence_refs,
            counterexample={
                "considered": "Every cached or locally stored artifact may be active.",
                "excluded": False,
                "basis": "Static filesystem presence does not establish current runtime selection.",
            },
            next_action_refs=(action,),
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
        if (candidate.effective_scope or {}).get("state") != "applicable":
            # Supplemental Codex-home and plugin-cache artifacts are useful
            # inventory, but cannot support a runtime duplicate/selection
            # conclusion until applicability is independently established.
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
            # both be listed. Divergent bodies require the manifest-bound semantic
            # panel, and even that panel cannot prove runtime selection or
            # causality. Preserve the occurrence without manufacturing an
            # inference while the provider panel remains pending.
            semantic_enabled = state.builder.modes["semantic"] == "enabled"
            _add_case(
                state,
                check_id="semantic.skill.duplicate-name-selection-risk",
                family="semantic",
                question=f"Do divergent same-name Skills {name!r} create a selection risk?",
                check_state=CheckState.NOT_RUN.value,
                reason={
                    "code": (
                        "semantic_provider_run_pending"
                        if semantic_enabled
                        else "semantic_mode_disabled"
                    ),
                    "runtime_selection_unobserved": True,
                    "expected": semantic_enabled,
                },
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
            if declaration.optional and resolution.status in {
                "missing",
                "unreadable",
                "unsupported_type",
            }:
                state.builder.add_check(
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    state=CheckState.PASS.value,
                    reason={
                        "code": "optional_reference_unavailable",
                        "detail": resolution.reason,
                        "optional_basis": declaration.optional_basis,
                        "taxonomy_exclusion": "intentionally_optional_reference",
                    },
                    evidence_refs=(declaration_evidence, resolution_evidence),
                    input_revisions=tuple(filter(None, (candidate.revision,))),
                )
                continue
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
                    counterexample={"considered": "The target may exist outside the scan or be intentionally optional.", "excluded": True, "basis": "The supported resolver and frozen package boundary decide validity without reading outside content, and explicit optional-reference contracts were excluded before this finding."},
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

            if resolution.status == "valid_directory":
                assert resolution.target_path is not None and resolution.normalized_target is not None
                resource = _add_resource_record(
                    state,
                    declaration_source=candidate,
                    target=resolution.target_path,
                    display=resolution.normalized_target,
                    status=SourceStatus.DISCOVERED.value,
                    reason=resolution.reason,
                )
                state.builder.add_check(
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    state=CheckState.PASS.value,
                    reason={"code": "reference_directory_valid"},
                    evidence_refs=(
                        declaration_evidence,
                        resolution_evidence,
                        state.source_evidence[resource.source_id],
                    ),
                    input_revisions=(candidate.revision or "unknown",),
                )
                continue

            assert resolution.target_path is not None and resolution.normalized_target is not None
            if resolution.target_path.suffix.casefold() in {
                ".avif",
                ".gif",
                ".ico",
                ".jpeg",
                ".jpg",
                ".pdf",
                ".png",
                ".svg",
                ".webp",
            }:
                resource = _add_resource_record(
                    state,
                    declaration_source=candidate,
                    target=resolution.target_path,
                    display=resolution.normalized_target,
                    status=SourceStatus.DISCOVERED.value,
                    reason="supported non-text resource resolved inside scope; content was not parsed as text",
                )
                state.builder.add_check(
                    check_id="deterministic.reference.validity",
                    family="references",
                    question=question,
                    state=CheckState.PASS.value,
                    reason={"code": "reference_non_text_resource_valid"},
                    evidence_refs=(
                        declaration_evidence,
                        resolution_evidence,
                        state.source_evidence[resource.source_id],
                    ),
                    input_revisions=(candidate.revision or "unknown",),
                )
                continue
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
            compatibility_status, compatibility_reason = (
                explicit_version_compatibility(content, target_read.content)
            )
            if compatibility_status == "incompatible":
                compatibility_evidence = state.builder.add_evidence(
                    kind=EvidenceKind.DERIVED.value,
                    producer=f"reference-compatibility@{RULE_SET_VERSION}",
                    summary=compatibility_reason,
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
                    reason={
                        "code": "explicit_version_incompatibility",
                        "detail": compatibility_reason,
                    },
                    source_refs=(candidate.source_id, resource.source_id),
                    dimension="reference_compatibility",
                    labels=("stale_reference",),
                    severity="high",
                    confidence="high",
                    evidence_refs=(declaration_evidence, state.source_evidence[resource.source_id], compatibility_evidence),
                    counterexample={"considered": "An older target may be intentionally pinned.", "excluded": True, "basis": "The target explicitly declares incompatibility with the required schema."},
                    next_action_refs=(action,),
                )
                continue
            if compatibility_status == "compatible":
                compatibility_evidence = state.builder.add_evidence(
                    kind=EvidenceKind.DERIVED.value,
                    producer=f"reference-compatibility@{RULE_SET_VERSION}",
                    summary=compatibility_reason,
                    source_refs=(candidate.source_id, resource.source_id),
                    parent_evidence_refs=(
                        declaration_evidence,
                        state.source_evidence[resource.source_id],
                    ),
                    rule_or_provider={
                        "rule_id": "reference.explicit-version-compatibility@0.1"
                    },
                    disclosure="location_only",
                )
                state.builder.add_check(
                    check_id="deterministic.reference.freshness",
                    family="maintenance",
                    question=(
                        f"Does {resolution.normalized_target} satisfy its declared "
                        "schema compatibility contract?"
                    ),
                    state=CheckState.PASS.value,
                    reason={
                        "code": "explicit_version_compatibility",
                        "detail": compatibility_reason,
                    },
                    evidence_refs=(
                        declaration_evidence,
                        state.source_evidence[resource.source_id],
                        compatibility_evidence,
                    ),
                    input_revisions=tuple(
                        filter(None, (candidate.revision, target_read.revision))
                    ),
                )
                continue
            if compatibility_status == "insufficient_evidence":
                action = state.builder.add_next_action(
                    kind="evidence_request",
                    summary=(
                        f"Add or review an explicit compatibility declaration for "
                        f"{resolution.normalized_target}; do not infer freshness from age."
                    ),
                    bounds={
                        "source": candidate.location,
                        "target": resolution.normalized_target,
                        "automatic_apply": False,
                    },
                )
                _add_case(
                    state,
                    check_id="deterministic.reference.freshness",
                    family="maintenance",
                    question=(
                        f"Does {resolution.normalized_target} satisfy its declared "
                        "schema compatibility contract?"
                    ),
                    check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
                    reason={
                        "code": "freshness_contract_incomplete",
                        "detail": compatibility_reason,
                        "mtime_used": False,
                        "expected": True,
                    },
                    source_refs=(candidate.source_id, resource.source_id),
                    dimension="maintenance_freshness",
                    confidence="high",
                    evidence_refs=(
                        declaration_evidence,
                        state.source_evidence[resource.source_id],
                    ),
                    counterexample={
                        "considered": "The reference may still be compatible.",
                        "excluded": False,
                        "basis": (
                            "The declared version facts do not decide compatibility; "
                            "timestamps were not used."
                        ),
                    },
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
        safe_key, _, _ = minimize_excerpt(key, limit=200)
        source_refs = tuple(sorted(item.source_ref for item in all_values[key]))
        parents = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"precedence-resolver@{RULE_SET_VERSION}",
            summary=f"Effective value for {safe_key} is unknown because project trust is unknown.",
            source_refs=source_refs,
            parent_evidence_refs=parents + (profile_evidence,),
            rule_or_provider={"rule_id": "codex.config.trust-gated-precedence@0.1"},
            disclosure="location_only",
        )
        action = state.builder.add_next_action(
            kind="evidence_request",
            summary="Rerun with --project-trust trusted or --project-trust untrusted after verifying Codex trust state.",
            bounds={"key": safe_key, "accepted_values": ["trusted", "untrusted"]},
        )
        _add_case(
            state,
            check_id="deterministic.configuration.precedence",
            family="precedence",
            question=f"Which configuration value governs {safe_key}?",
            check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
            reason={"code": "project_trust_unknown", "missing_evidence": "Codex project trust state", "expected": True},
            source_refs=source_refs,
            dimension=f"configuration:{safe_key}",
            confidence="high",
            evidence_refs=parents + (profile_evidence, derived),
            counterexample={"considered": "The closest project file wins.", "excluded": False, "basis": "Project layers are skipped when untrusted, and trust was not supplied."},
            next_action_refs=(action,),
        )
    for key, values in all_values.items():
        safe_key, _, _ = minimize_excerpt(key, limit=200)
        effective_values = [item for item in values if item.applicability == "applicable"]
        if len(effective_values) < 2 or key not in winners:
            continue
        source_refs = tuple(sorted(item.source_ref for item in effective_values))
        claim_refs = tuple(
            sorted(
                claim.claim_id
                for source_ref in source_refs
                for claim in state.parsed[source_ref].claims
                if claim.dimension == f"configuration:{safe_key}"
            )
        )
        parents = tuple(state.source_evidence[source_ref] for source_ref in source_refs)
        winner = winners[key]
        derived = state.builder.add_evidence(
            kind=EvidenceKind.DERIVED.value,
            producer=f"precedence-resolver@{RULE_SET_VERSION}",
            summary=f"Configuration key {safe_key} is governed by {winner.source_ref} under the reviewed layer order.",
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
            question=f"Which effective source governs configuration key {safe_key}?",
            check_state=CheckState.PASS.value,
            reason={"code": "precedence_resolved", "winner_source_ref": winner.source_ref},
            source_refs=source_refs,
            claim_refs=claim_refs,
            region=region,
            dimension=f"configuration:{safe_key}",
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
        and (item.effective_scope or {}).get("state") == "applicable"
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


def _semantic_coverage(state: _PipelineState, request: AnalysisRequest) -> None:
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
        return

    if request.semantic_not_applicable_reason is not None:
        selected_refs = tuple(sorted(request.semantic_not_applicable_source_refs))
        parent_source_evidence = tuple(
            state.source_evidence[source_ref]
            for source_ref in selected_refs
            if source_ref in state.source_evidence
        )
        _add_case(
            state,
            check_id="semantic.skill.relationship-applicability",
            family="semantic",
            question=(
                "Was cross-Skill semantic relationship analysis applicable to "
                "the selected Skill set?"
            ),
            check_state=CheckState.PASS.value,
            reason={
                "code": "semantic_relationship_scope_not_applicable",
                "detail": request.semantic_not_applicable_reason,
                "selected_skill_count": len(selected_refs),
                "provider_started": False,
                "expected": True,
            },
            source_refs=selected_refs,
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence,) + parent_source_evidence,
            counterexample={
                "considered": "A cross-Skill relationship may still exist.",
                "excluded": True,
                "basis": "Fewer than two Skills were selected, so no pair exists.",
            },
        )
        return

    manifest = request.semantic_manifest
    response = request.semantic_response
    invocation = request.semantic_invocation
    consent_digest = request.semantic_consent_digest
    if manifest is None or response is None or invocation is None:
        _add_case(
            state,
            check_id="semantic.skill.relationship",
            family="semantic",
            question="Was a manifest-bound semantic Skill relationship response available?",
            check_state=CheckState.NOT_RUN.value,
            reason={
                "code": "semantic_provider_run_pending",
                "expected": True,
                "required": [
                    "exact disclosure manifest",
                    "digest-bound one-run or standalone authorization",
                    "validated provider invocation",
                    "provider response",
                ],
            },
            source_refs=(),
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence,),
            counterexample={
                "considered": "No semantic relationship exists.",
                "excluded": True,
                "basis": "The provider check did not start, so absence was not tested.",
            },
        )
        return

    manifest_errors = validate_manifest_digest(manifest)
    expected_digest = manifest.get("manifest_digest")
    if consent_digest != expected_digest:
        manifest_errors.append(
            "consent digest does not exactly match the disclosure manifest"
        )
    current_graph = state.builder.to_unsealed_dict("complete_with_gaps")
    manifest_errors.extend(validate_manifest_against_graph(manifest, current_graph))
    if manifest_errors:
        current_source_refs = {
            item.source_id for item in state.builder.sources
        }
        _add_case(
            state,
            check_id="semantic.skill.relationship",
            family="semantic",
            question="Could the disclosed semantic request start against the current inputs?",
            check_state=CheckState.NOT_RUN.value,
            reason={
                "code": "semantic_manifest_or_consent_invalid",
                "expected": True,
                "detail": sorted(set(manifest_errors)),
            },
            source_refs=tuple(
                sorted(
                    current_source_refs.intersection(
                        manifest.get("source_selection", {}).get(
                            "selected_source_refs", []
                        )
                    )
                )
            ),
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence,),
            counterexample={
                "considered": "The prior response may still describe current content.",
                "excluded": False,
                "basis": "Content or consent identity must match exactly; it is never guessed.",
            },
            completeness="partial",
        )
        return

    invocation_errors: list[str] = []
    if invocation.get("status") != "completed":
        invocation_errors.append("provider invocation did not complete")
    if invocation.get("consent_manifest_digest") != expected_digest:
        invocation_errors.append("provider invocation consent identity mismatch")
    if invocation.get("provider") != manifest.get("provider"):
        invocation_errors.append("provider invocation identity mismatch")
    if invocation.get("model") != manifest.get("model"):
        invocation_errors.append("provider invocation model identity mismatch")
    if invocation.get("reasoning_effort") != manifest.get("reasoning_effort"):
        invocation_errors.append("provider invocation effort identity mismatch")
    if invocation.get("selection_digest") != manifest.get("selection", {}).get(
        "selection_digest"
    ):
        invocation_errors.append("provider invocation selection identity mismatch")
    if invocation.get("response_digest") != semantic_response_digest(response):
        invocation_errors.append("provider invocation response digest mismatch")
    if invocation.get("tool_activity_observed"):
        invocation_errors.append("provider invocation used a forbidden tool")
    calls = invocation.get("calls")
    if (
        not isinstance(calls, list)
        or len(calls) != 3
        or [item.get("role") for item in calls if isinstance(item, dict)]
        != ["analyst_a", "analyst_b", "judge"]
        or any(
            not isinstance(item, dict)
            or item.get("fresh_ephemeral_context") is not True
            for item in calls or []
        )
    ):
        invocation_errors.append(
            "provider invocation did not establish three fresh panel contexts"
        )
    elif (
        calls[0].get("source_order") != "canonical"
        or calls[1].get("source_order") != "reversed"
        or calls[0].get("execution_group") != "parallel_analysts"
        or calls[1].get("execution_group") != "parallel_analysts"
        or calls[0].get("blind_to_peer") is not True
        or calls[1].get("blind_to_peer") is not True
        or calls[2].get("starts_after") != ["analyst_a", "analyst_b"]
    ):
        invocation_errors.append("provider invocation panel source order mismatch")
    elif (
        isinstance(response.get("analysts"), dict)
        and isinstance(response["analysts"].get("analyst_a"), dict)
        and isinstance(response["analysts"].get("analyst_b"), dict)
        and isinstance(response.get("judge"), dict)
    ):
        expected_call_digests = [
            semantic_response_digest(response["analysts"]["analyst_a"]),
            semantic_response_digest(response["analysts"]["analyst_b"]),
            semantic_response_digest(response["judge"]),
        ]
        if [item.get("response_digest") for item in calls] != expected_call_digests:
            invocation_errors.append("provider invocation call digest mismatch")
    response_errors = validate_provider_response(response, manifest)
    errors = sorted(set(invocation_errors + response_errors))
    selected_refs = tuple(
        sorted(
            manifest.get("source_selection", {}).get(
                "selected_source_refs", []
            )
        )
    )
    semantic_source_selection = {
        "selected_source_refs": list(selected_refs),
        "requested_source_refs": list(
            manifest.get("source_selection", {}).get(
                "requested_source_refs", []
            )
        ),
        "question_limit_omitted_source_refs": list(
            manifest.get("source_selection", {}).get(
                "question_limit_omitted_source_refs", []
            )
        ),
    }
    semantic_question_coverage = dict(
        manifest.get("semantic_panel", {}).get("coverage", {})
    )
    semantic_disclosure = {
        "content_handle_count": len(manifest.get("content_handles", [])),
        "disclosed_claim_count": sum(
            len(item.get("claims", []))
            for item in manifest.get("content_handles", [])
            if isinstance(item, dict)
        ),
        "exclusion_counts": dict(
            manifest.get("exclusions", {}).get("counts", {})
        ),
        "retention_and_cache": dict(manifest.get("retention_and_cache", {})),
    }
    parent_source_evidence = tuple(
        state.source_evidence[source_ref]
        for source_ref in selected_refs
        if source_ref in state.source_evidence
    )
    if errors:
        call = dict(invocation)
        call["status"] = "unusable"
        call["response_validation"] = errors
        call["source_selection"] = semantic_source_selection
        call["question_coverage"] = semantic_question_coverage
        call["disclosure_summary"] = semantic_disclosure
        state.builder.semantic_calls.append(call)
        _add_case(
            state,
            check_id="semantic.skill.relationship",
            family="semantic",
            question="Did the started semantic provider call return usable cited evidence?",
            check_state=CheckState.ERROR.value,
            reason={
                "code": "semantic_provider_response_unusable",
                "expected": True,
                "detail": errors,
            },
            source_refs=selected_refs,
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence,) + parent_source_evidence,
            counterexample={
                "considered": "The malformed output may contain a correct opinion.",
                "excluded": False,
                "basis": "Unvalidated or overreaching provider output is never product evidence.",
            },
            completeness="partial",
        )
        return

    call = dict(invocation)
    call["response_validation"] = "valid"
    call["evidence_kind"] = EvidenceKind.INFERRED.value
    call["local_final_adjudication"] = True
    call["source_selection"] = semantic_source_selection
    call["question_coverage"] = semantic_question_coverage
    call["disclosure_summary"] = semantic_disclosure
    state.builder.semantic_calls.append(call)
    analyst_a = response["analysts"]["analyst_a"]
    analyst_b = response["analysts"]["analyst_b"]
    judge = response["judge"]
    summary_excerpt = minimize_excerpt(
        (
            f"Analyst A: {analyst_a['summary']} "
            f"Analyst B: {analyst_b['summary']} Judge: {judge['summary']}"
        ),
        limit=480,
    )[0]
    response_evidence = state.builder.add_evidence(
        kind=EvidenceKind.INFERRED.value,
        producer="codex-desktop-semantic-panel@0.3",
        summary=summary_excerpt,
        source_refs=selected_refs,
        parent_evidence_refs=parent_source_evidence,
        rule_or_provider={
            "source_kind": "model",
            "provider": manifest["provider"],
            "model": manifest["model"],
            "reasoning_effort": manifest["reasoning_effort"],
            "consent_manifest_digest": expected_digest,
            "selection_digest": manifest["selection"]["selection_digest"],
            "qualification": manifest["qualification"],
        },
        disclosure="excerpt",
        excerpt=summary_excerpt,
    )
    state.builder.add_check(
        check_id="semantic.provider.response",
        family="semantic",
        question="Did the consented semantic provider return a valid bounded response?",
        state=CheckState.PASS.value,
        reason={
            "code": "semantic_provider_response_valid",
            "question_count": len(analyst_a["answers"]),
            "analyst_a_answer_count": len(analyst_a["answers"]),
            "analyst_b_answer_count": len(analyst_b["answers"]),
            "judge_judgment_count": len(judge["judgments"]),
            "release_qualified": manifest["qualification"]["release_qualified"],
        },
        evidence_refs=(mode_evidence, response_evidence),
        input_revisions=tuple(
            item["revision"] for item in manifest["content_handles"]
        ),
    )

    coverage = semantic_question_coverage
    if not coverage.get("complete", False):
        _add_case(
            state,
            check_id="semantic.skill.relationship-coverage",
            family="semantic",
            question="Did the bounded semantic panel cover every eligible pair and dimension?",
            check_state=CheckState.INSUFFICIENT_EVIDENCE.value,
            reason={
                "code": "bounded_semantic_question_limit",
                "expected": True,
                "eligible_question_count": coverage.get("eligible_question_count"),
                "emitted_question_count": coverage.get("emitted_question_count"),
                "omitted_question_count": coverage.get("omitted_question_count"),
                "question_limit_omitted_source_refs": manifest.get(
                    "source_selection", {}
                ).get("question_limit_omitted_source_refs", []),
            },
            source_refs=selected_refs,
            dimension="semantic_coverage",
            evidence_refs=(mode_evidence, response_evidence),
            counterexample={
                "considered": "Unasked pair/dimension questions may contain a material relationship.",
                "excluded": False,
                "basis": "The omission is explicit and is never treated as a pass.",
            },
            completeness="partial",
        )

    source_records = {item.source_id: item for item in state.builder.sources}
    analyst_b_by_question = {
        item["question_id"]: item for item in analyst_b["answers"]
    }
    judgments_by_question = {
        item["question_id"]: item for item in judge["judgments"]
    }
    grouped: dict[tuple[tuple[str, ...], str], list[dict[str, Any]]] = {}
    for answer in analyst_a["answers"]:
        joined = {
            "analyst_a": answer,
            "analyst_b": analyst_b_by_question[answer["question_id"]],
            "judge": judgments_by_question[answer["question_id"]],
        }
        key = (tuple(sorted(answer["source_refs"])), answer["dimension"])
        grouped.setdefault(key, []).append(joined)

    for (source_refs, dimension), relations in sorted(grouped.items()):
        claim_refs = tuple(
            sorted(
                {
                    claim_ref
                    for relation in relations
                    for role in ("analyst_a", "analyst_b", "judge")
                    for claim_ref in relation[role]["claim_refs"]
                }
            )
        )
        analyst_a_labels = tuple(
            sorted({relation["analyst_a"]["label"] for relation in relations})
        )
        analyst_b_labels = tuple(
            sorted({relation["analyst_b"]["label"] for relation in relations})
        )
        judge_labels = tuple(
            sorted(
                {
                    relation["judge"]["selected_label"]
                    for relation in relations
                    if relation["judge"]["selected_label"] is not None
                }
            )
        )
        locations = [
            source_records[source_ref].location
            for source_ref in source_refs
            if source_ref in source_records
        ]
        applicable = all(
            source_records[source_ref].effective_scope.get("state") == "applicable"
            for source_ref in source_refs
            if source_ref in source_records
        ) and len(locations) == len(source_refs)
        region = {
            "paths": locations,
            "intersection": "proven" if applicable else "unknown",
            "runtime_observed": False,
            "witness": "locally resolved static applicability and cited Skill claims only",
        }
        relation_evidence: list[str] = []
        for relation in relations:
            answer_a = relation["analyst_a"]
            answer_b = relation["analyst_b"]
            judgment = relation["judge"]
            parents = tuple(
                sorted(
                    {
                        *(
                            state.source_evidence[source_ref]
                            for source_ref in answer_a["source_refs"]
                            if source_ref in state.source_evidence
                        ),
                        *(
                            state.claim_evidence[claim_ref]
                            for claim_ref in claim_refs
                            if claim_ref in state.claim_evidence
                        ),
                    }
                )
            )
            for role, answer in (
                ("analyst_a", answer_a),
                ("analyst_b", answer_b),
            ):
                rationale = minimize_excerpt(answer["rationale"], limit=480)[0]
                relation_evidence.append(
                    state.builder.add_evidence(
                        kind=EvidenceKind.INFERRED.value,
                        producer=f"codex-desktop-semantic-{role}@0.3",
                        summary=rationale,
                        source_refs=tuple(sorted(answer["source_refs"])),
                        parent_evidence_refs=parents,
                        rule_or_provider={
                            "source_kind": "model",
                            "provider": manifest["provider"],
                            "model": manifest["model"],
                            "panel_role": role,
                            "answer_id": answer["answer_id"],
                            "question_id": answer["question_id"],
                            "label_hypothesis": answer["label"],
                            "citations": answer["citations"],
                            "consent_manifest_digest": expected_digest,
                        },
                        disclosure="excerpt",
                        excerpt=rationale,
                    )
                )
            judge_rationale = minimize_excerpt(judgment["rationale"], limit=480)[0]
            relation_evidence.append(
                state.builder.add_evidence(
                    kind=EvidenceKind.INFERRED.value,
                    producer="codex-desktop-semantic-judge@0.3",
                    summary=judge_rationale,
                    source_refs=tuple(sorted(judgment["source_refs"])),
                    parent_evidence_refs=parents,
                    rule_or_provider={
                        "source_kind": "model",
                        "provider": manifest["provider"],
                        "model": manifest["model"],
                        "panel_role": "judge",
                        "judgment_id": judgment["judgment_id"],
                        "analyst_a_answer_id": judgment["analyst_a_answer_id"],
                        "analyst_b_answer_id": judgment["analyst_b_answer_id"],
                        "question_id": judgment["question_id"],
                        "disposition": judgment["disposition"],
                        "label_hypothesis": judgment["selected_label"],
                        "citations": judgment["citations"],
                        "consent_manifest_digest": expected_digest,
                    },
                    disclosure="excerpt",
                    excerpt=judge_rationale,
                )
            )

        if len(relations) != 1:
            raise ValueError("semantic panel emitted duplicate pair/dimension questions")
        relation = relations[0]
        panel_decision = adjudicate_panel_answers(
            relation["analyst_a"],
            relation["analyst_b"],
            relation["judge"],
            shared_region_established=applicable,
        )
        panel_agrees = bool(panel_decision["agreement"])
        has_open_counterexample = bool(panel_decision["counterexample_open"])
        has_missing_evidence = bool(panel_decision["missing_evidence"])
        decisive = bool(panel_decision["decisive"])
        labels = tuple(panel_decision["labels"])
        qualifiers: tuple[ValidationQualifier, ...] = ()
        check_state = str(panel_decision["state"])
        severity = panel_decision["severity"]
        potential = panel_decision["potential_severity"]
        confidence = panel_decision["confidence"]
        if panel_decision["runtime_validation_needed"]:
            qualifiers = (
                ValidationQualifier(
                    "runtime_validation_needed",
                    "The overlapping Skill scopes are jointly available for one task.",
                    "Observe both sources as applicable to the same task.",
                    "Establish mutually exclusive routing or applicability.",
                ),
            )

        counterexample_text = "; ".join(
            explanation
            for relation in relations
            for explanation in (
                relation["analyst_a"]["counterexample"]["explanation"],
                relation["analyst_b"]["counterexample"]["explanation"],
                relation["judge"]["counterexample"]["explanation"],
            )
            if explanation
        )
        missing = sorted(
            {
                item
                for relation in relations
                for item in (
                    list(relation["analyst_a"]["missing_evidence"])
                    + list(relation["analyst_b"]["missing_evidence"])
                    + list(relation["judge"]["missing_evidence"])
                )
            }
        )
        action_refs: tuple[str, ...] = ()
        recommendation_decision = relation["judge"]["recommendation_decision"]
        recommendation_role = recommendation_decision["selected_from"]
        recommendation_answer = (
            relation[recommendation_role]
            if recommendation_role in {"analyst_a", "analyst_b"}
            else None
        )
        accepted_recommendations = []
        if (
            decisive
            and recommendation_answer is not None
            and recommendation_answer.get("recommendation") is not None
            and recommendation_decision["disposition"] == "accepted"
            and relation["judge"]["selected_label"] == recommendation_answer["label"]
            and recommendation_is_compatible(
                recommendation_answer["label"],
                recommendation_answer["recommendation"]["kind"],
            )
            and recommendation_answer["recommendation"]["kind"] != "no_action"
        ):
            accepted_recommendations.append(recommendation_answer["recommendation"])
        recommendation_discarded = (
            recommendation_role in {"analyst_a", "analyst_b"}
            and not accepted_recommendations
        )
        if accepted_recommendations:
            recommendation = accepted_recommendations[0]
            action_refs = (
                state.builder.add_next_action(
                    kind="manual_repair",
                    summary=recommendation["summary"],
                    bounds={
                        "source_refs": list(source_refs),
                        "dimension": dimension,
                        "proposal_kind": recommendation["kind"],
                        "expected_benefit": recommendation["expected_benefit"],
                        "risk": recommendation["risk"],
                        "verification": recommendation["verification"],
                        "model_proposed": True,
                        "automatic_apply": False,
                    },
                ),
            )
        elif check_state in {
            CheckState.FINDING.value,
            CheckState.CANDIDATE.value,
            CheckState.INSUFFICIENT_EVIDENCE.value,
        }:
            action_refs = (
                state.builder.add_next_action(
                    kind=(
                        "manual_validation"
                        if check_state == CheckState.FINDING.value
                        else "evidence_request"
                    ),
                    summary=(
                        "Review the cited Skill excerpts and their routing boundaries; "
                        "make no automatic change and capture task-specific applicability "
                        "evidence before asserting runtime impact."
                    ),
                    bounds={
                        "source_refs": list(source_refs),
                        "dimension": dimension,
                        "missing_evidence": missing,
                        "panel_agreement": panel_agrees,
                        "resolution_kind": panel_decision["resolution_kind"],
                        "automatic_apply": False,
                    },
                ),
            )
        _add_case(
            state,
            check_id="semantic.skill.relationship",
            family="semantic",
            question=(
                "What material semantic relationship exists among the selected "
                f"Skills on {dimension}?"
            ),
            check_state=check_state,
            reason={
                "code": "local_semantic_panel_adjudication",
                "question_ids": sorted(
                    {relation["analyst_a"]["question_id"] for relation in relations}
                ),
                "analyst_a_labels": list(analyst_a_labels),
                "analyst_b_labels": list(analyst_b_labels),
                "judge_labels": list(judge_labels),
                "judge_dispositions": sorted(
                    {
                        relation["judge"]["disposition"]
                        for relation in relations
                    }
                ),
                "panel_agreement": panel_agrees,
                "analyst_agreement": panel_decision["analyst_agreement"],
                "resolved_disagreement": panel_decision["resolved_disagreement"],
                "resolution_kind": panel_decision["resolution_kind"],
                "counterexample_open": has_open_counterexample,
                "missing_evidence": missing,
                "manual_recommendation_accepted": bool(accepted_recommendations),
                "manual_recommendation_discarded": recommendation_discarded,
                "release_qualified": manifest["qualification"]["release_qualified"],
                "runtime_causality_asserted": False,
                "shared_applicability_region_established": applicable,
            },
            source_refs=source_refs,
            claim_refs=claim_refs,
            region=region,
            dimension=dimension,
            labels=labels,
            qualifiers=qualifiers,
            severity=severity,
            potential_severity=potential,
            confidence=confidence,
            evidence_refs=tuple(sorted(set(relation_evidence))),
            counterexample={
                "considered": counterexample_text or "No counterexample supplied.",
                "excluded": not has_open_counterexample,
                "basis": (
                    "Both blind analysts and the fresh judge were joined by frozen "
                    "question identity and locally interpreted; static evidence "
                    "does not establish runtime causality."
                ),
            },
            next_action_refs=action_refs,
            completeness="complete" if decisive else "partial",
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
            semantic_manifest_digest=(
                request.semantic_manifest.get("manifest_digest")
                if request.semantic_manifest is not None
                else None
            ),
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
    _local_observed_applicability_checks(state)
    _duplicate_checks(state)
    _reference_checks(state)
    effective_config = _configuration_precedence_checks(state)
    _instruction_budget_check(state, effective_config)
    _skill_budget_abstention(state)
    _semantic_coverage(state, request)
    _group_cases(state)
    graph = builder.seal()
    return AnalysisResponse(graph, scope)
