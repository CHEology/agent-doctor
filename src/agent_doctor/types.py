"""Closed vocabularies from the Stage 01-04 contracts."""

from __future__ import annotations

from enum import StrEnum


class CheckState(StrEnum):
    PASS = "pass"
    FINDING = "finding"
    CANDIDATE = "candidate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_RUN = "not_run"
    ERROR = "error"


class EvidenceKind(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    INFERRED = "inferred"
    RUNTIME = "runtime"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RunOutcome(StrEnum):
    COMPLETE = "complete"
    COMPLETE_WITH_GAPS = "complete_with_gaps"
    EXECUTION_FAILED = "execution_failed"


class CIOutcome(StrEnum):
    SATISFIED = "satisfied"
    POLICY_FAILED = "policy_failed"
    EXECUTION_FAILED = "execution_failed"


class SourceStatus(StrEnum):
    DISCOVERED = "discovered"
    IGNORED = "ignored"
    SHADOWED = "shadowed"
    TRUNCATED = "truncated"
    MISSING = "missing"
    UNREADABLE = "unreadable"
    EXCLUDED = "excluded"


class SourceType(StrEnum):
    SKILL_MANIFEST = "skill_manifest"
    SKILL_BODY = "skill_body"
    INSTRUCTION = "instruction"
    OVERRIDE = "override"
    CONFIG = "config"
    RESOURCE = "resource"
    SCRIPT = "script"
    OTHER = "other"


SUBSTANTIVE_LABELS = frozenset(
    {
        "semantic_conflict",
        "scope_overlap",
        "behavioral_redundancy",
        "complementarity",
        "precedence_override",
        "invalid_reference",
        "stale_reference",
        "context_budget_risk",
        "configuration_risk",
        "no_material_relation",
    }
)

VALIDATION_QUALIFIERS = frozenset({"runtime_validation_needed"})

SEVERITY_RANK = {
    Severity.INFO.value: 0,
    Severity.LOW.value: 1,
    Severity.MEDIUM.value: 2,
    Severity.HIGH.value: 3,
    Severity.CRITICAL.value: 4,
}

CONFIDENCE_RANK = {
    Confidence.LOW.value: 0,
    Confidence.MEDIUM.value: 1,
    Confidence.HIGH.value: 2,
}
