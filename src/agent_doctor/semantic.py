"""Strict, local-only semantic contract used by synthetic qualification cases.

The Stage 05 product CLI does not expose semantic analysis.  This module exists
for the reviewed Stage 04 synthetic fixtures and deliberately has no network
adapter, credentials, or cross-run cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .canonical import content_digest, digest, stable_id
from .privacy import minimize_excerpt, redact_secrets
from .types import SUBSTANTIVE_LABELS
from .version import SEMANTIC_CONTRACT_VERSION, TAXONOMY_VERSION


FIXTURE_CONSENT = "manifest-specific synthetic-content consent"
SCRIPTED_PROVIDER = "scripted-neutral-provider"
SCRIPTED_MODEL = "fixture-rule-model/0.1"


@dataclass(frozen=True)
class DisclosureBuild:
    manifest: dict[str, Any] | None
    blockers: tuple[str, ...]


def build_fixture_disclosure(case: dict[str, Any], *, purpose: str) -> DisclosureBuild:
    """Create an exact per-call manifest or refuse before provider start."""

    if case.get("modes", {}).get("semantic") != "enabled":
        return DisclosureBuild(None, ("semantic mode is not enabled",))
    provider = case.get("inputs", {}).get("provider", {})
    provider_kind = provider.get("kind") or provider.get("provider")
    if provider_kind != SCRIPTED_PROVIDER:
        return DisclosureBuild(None, ("provider identity is not the reviewed local scripted provider",))
    consent = case.get("boundaries", {}).get("consent")
    if consent != FIXTURE_CONSENT:
        return DisclosureBuild(None, ("consent text does not exactly match the fixture disclosure contract",))

    handles: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for file in case.get("inputs", {}).get("files", []):
        path = str(file.get("path", "unknown"))
        policy = file.get("policy", {})
        content = file.get("content")
        if file.get("source_type") == "script" or policy.get("executable"):
            exclusions.append({"path": path, "reason": "script and executable bodies are never submitted"})
            continue
        if policy.get("semantic_disclosure") != "allowed":
            exclusions.append({"path": path, "reason": "semantic disclosure is not authorized"})
            continue
        if not isinstance(content, str):
            exclusions.append({"path": path, "reason": "no readable content exists"})
            continue
        redaction = redact_secrets(content)
        if redaction.categories:
            exclusions.append({"path": path, "reason": "secret-bearing content is excluded, not merely masked for a model"})
            continue
        excerpt, _, disclosure_kind = minimize_excerpt(content, limit=360)
        was_minimized = len(content.strip()) > 360
        handle_id = stable_id(
            "handle",
            {"path": path, "revision": content_digest(content), "purpose": purpose, "excerpt": excerpt},
        )
        handles.append(
            {
                "handle_id": handle_id,
                "path": path,
                "revision": content_digest(content),
                "excerpt": excerpt,
                "minimized": was_minimized,
                "disclosure": disclosure_kind,
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": "agent-doctor-semantic-disclosure/0.1",
        "provider": SCRIPTED_PROVIDER,
        "model": SCRIPTED_MODEL,
        "network": "simulated-local-only",
        "retention": provider.get("retention", "unknown"),
        "purpose": purpose,
        "content_handles": sorted(handles, key=lambda item: item["path"]),
        "exclusions": sorted(exclusions, key=lambda item: item["path"]),
        "consent": consent,
        "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "cache": "disabled",
    }
    manifest["manifest_digest"] = digest(manifest)
    blockers: list[str] = []
    eligible_paths = {
        str(item.get("path"))
        for item in case.get("inputs", {}).get("files", [])
        if item.get("source_type") in {"skill_body", "skill_manifest", "instruction", "override"}
    }
    disclosed_paths = {item["path"] for item in handles}
    if eligible_paths and not disclosed_paths:
        blockers.append("all potentially decisive semantic content was withheld or excluded")
    return DisclosureBuild(manifest, tuple(blockers))


def validate_provider_response(response: Any, manifest: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(response, dict):
        return False, "provider response must be an object"
    required = {"labels", "confidence", "rationale", "citations", "counterexample_status"}
    missing = sorted(required - response.keys())
    if missing:
        return False, f"provider response missing fields: {', '.join(missing)}"
    labels = response.get("labels")
    if not isinstance(labels, list) or any(item not in SUBSTANTIVE_LABELS for item in labels):
        return False, "provider response contains an unknown substantive label"
    if response.get("confidence") not in {"high", "medium", "low"}:
        return False, "provider response contains invalid confidence"
    if response.get("counterexample_status") not in {"excluded", "open", "unknown"}:
        return False, "provider response contains invalid counterexample status"
    citations = response.get("citations")
    allowed = {item["handle_id"] for item in manifest.get("content_handles", [])}
    if not isinstance(citations, list) or not citations or any(item not in allowed for item in citations):
        return False, "provider response is uncited or cites an undisclosed handle"
    return True, "valid"


def invoke_fixture_provider(
    manifest: dict[str, Any],
    classifier: Callable[[list[str]], dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Invoke a pure local script and retain only inferred provenance."""

    excerpts = [item["excerpt"] for item in manifest["content_handles"]]
    call = {
        "provider": manifest["provider"],
        "model": manifest["model"],
        "contract_version": SEMANTIC_CONTRACT_VERSION,
        "input_digest": digest(
            {
                "manifest_digest": manifest["manifest_digest"],
                "handles": [item["handle_id"] for item in manifest["content_handles"]],
            }
        ),
        "consent_manifest_digest": manifest["manifest_digest"],
        "cache": "disabled",
        "status": "started",
        "retry_count": 0,
    }
    try:
        response = classifier(excerpts)
    except Exception as exc:  # controlled fixture adapter boundary
        call["status"] = "error"
        call["safe_error"] = type(exc).__name__
        return None, call
    valid, reason = validate_provider_response(response, manifest)
    call["status"] = "completed" if valid else "unusable"
    call["response_validation"] = reason
    if not valid:
        return None, call
    response = dict(response)
    response["evidence_kind"] = "inferred"
    response["provider_attribution"] = {
        "source_kind": "model",
        "provider": manifest["provider"],
        "model": manifest["model"],
        "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
    }
    return response, call
