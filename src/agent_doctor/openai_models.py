"""Reviewed OpenAI model capabilities, safe selection, and source drift checks.

This module deliberately does not call a model.  Runtime selection consumes a
reviewed local profile, while the optional documentation check only detects a
candidate change in allowlisted official Markdown sources.  A documentation
change never promotes a model or establishes product qualification by itself.
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .canonical import content_digest, digest, stable_id
from .jsonschema_subset import SchemaError, validate


PROFILE_SCHEMA_VERSION = "agent-doctor-openai-model-profile/0.1"
DECISION_SCHEMA_VERSION = "agent-doctor-model-selection/0.1"
DOC_CHECK_SCHEMA_VERSION = "agent-doctor-openai-doc-check/0.1"
ROUTING_SUITE_SCHEMA_VERSION = "agent-doctor-model-routing-test/0.1"
OFFICIAL_SOURCE_HOSTS = frozenset({"developers.openai.com", "platform.openai.com"})
REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})
SELECTION_STRATEGIES = frozenset({"auto", "pinned"})
MAX_OFFICIAL_DOCUMENT_BYTES = 2 * 1024 * 1024


class ModelProfileError(ValueError):
    """Raised when a model profile or selection input violates its contract."""


class _OfficialRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        if not _is_official_uri(newurl) or not newurl.endswith(".md"):
            raise ModelProfileError("official source redirected outside the allowlisted Markdown boundary")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class ModelSelectionRequest:
    capability: str
    strategy: str = "auto"
    requested_model: str | None = None
    reasoning_effort: str | None = None
    available_models: frozenset[str] | None = None
    require_qualified: bool = False
    availability_basis: str = "api_project_models"


def _parse_date(value: Any, *, field: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be an RFC 3339 full-date")
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be an RFC 3339 full-date")
        return None
    if parsed.isoformat() != value:
        errors.append(f"{field} must be an RFC 3339 full-date")
        return None
    return parsed


def _is_official_uri(uri: Any) -> bool:
    if not isinstance(uri, str):
        return False
    parsed = urlparse(uri)
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_SOURCE_HOSTS


def validate_model_profile(profile: Mapping[str, Any]) -> list[str]:
    """Return deterministic validation errors for a reviewed model profile."""

    errors: list[str] = []
    required = {
        "profile_schema_version",
        "profile_id",
        "profile_version",
        "provider",
        "status",
        "captured_at",
        "review_after",
        "provenance",
        "availability_contract",
        "qualifications",
        "capabilities",
        "review",
    }
    missing = sorted(required - set(profile))
    if missing:
        errors.append(f"missing model profile fields: {', '.join(missing)}")
    if profile.get("profile_schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append("unsupported model profile schema version")
    if profile.get("provider") != "openai":
        errors.append("only the OpenAI provider is supported by this profile contract")
    if profile.get("status") not in {"candidate", "reviewed", "stale", "incompatible"}:
        errors.append("unknown model profile status")
    captured_at = _parse_date(profile.get("captured_at"), field="captured_at", errors=errors)
    review_after = _parse_date(profile.get("review_after"), field="review_after", errors=errors)
    if captured_at is not None and review_after is not None and review_after < captured_at:
        errors.append("review_after cannot precede captured_at")

    provenance = profile.get("provenance")
    source_ids: set[str] = set()
    if not isinstance(provenance, list) or not provenance:
        errors.append("model profile has no provenance")
    else:
        for index, source in enumerate(provenance):
            if not isinstance(source, dict):
                errors.append(f"provenance[{index}] must be an object")
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                errors.append(f"provenance[{index}] has no source_id")
            elif source_id in source_ids:
                errors.append(f"duplicate provenance source_id: {source_id}")
            else:
                source_ids.add(source_id)
            if not _is_official_uri(source.get("uri")):
                errors.append(f"provenance[{index}] is not an allowlisted official OpenAI URI")
            expected_digest = source.get("content_digest")
            if not isinstance(expected_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is None:
                errors.append(f"provenance[{index}] has no valid content digest")
            if not source.get("assertions"):
                errors.append(f"provenance[{index}] has no reviewed assertions")
            watch = source.get("watch")
            if not isinstance(watch, dict) or watch.get("kind") not in {
                "latest_model",
                "model_catalog",
                "model_page",
                "models_api",
            }:
                errors.append(f"provenance[{index}] has no supported watch contract")

    availability = profile.get("availability_contract")
    if not isinstance(availability, dict):
        errors.append("availability_contract must be an object")
    else:
        if availability.get("endpoint") != "GET /v1/models":
            errors.append("availability_contract must use GET /v1/models")
        if availability.get("proves_ranking") is not False:
            errors.append("account availability must not be treated as a model ranking")

    qualifications = profile.get("qualifications")
    if not isinstance(qualifications, dict):
        errors.append("qualifications must be an object")
        qualifications = {}

    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        errors.append("model profile has no capabilities")
    else:
        for capability, contract in capabilities.items():
            if not isinstance(contract, dict):
                errors.append(f"capability {capability!r} must be an object")
                continue
            default_model = contract.get("default_model")
            candidates = contract.get("candidates")
            if not isinstance(default_model, str) or not default_model:
                errors.append(f"capability {capability!r} has no default_model")
            if not isinstance(candidates, list) or not candidates:
                errors.append(f"capability {capability!r} has no candidates")
                continue
            candidate_ids: set[str] = set()
            for index, candidate in enumerate(candidates):
                if not isinstance(candidate, dict):
                    errors.append(f"capability {capability!r} candidate[{index}] must be an object")
                    continue
                model_id = candidate.get("model")
                if not isinstance(model_id, str) or not model_id:
                    errors.append(f"capability {capability!r} candidate[{index}] has no model")
                elif model_id in candidate_ids:
                    errors.append(f"capability {capability!r} has duplicate candidate {model_id!r}")
                else:
                    candidate_ids.add(model_id)
                source_refs = candidate.get("source_refs")
                if not isinstance(source_refs, list) or not source_refs:
                    errors.append(f"candidate {model_id!r} has no source_refs")
                elif not set(source_refs).issubset(source_ids):
                    errors.append(f"candidate {model_id!r} cites an unknown source")
                qualification = candidate.get("qualification")
                if qualification not in {"not_required_advisory", "not_performed", "qualified", "failed"}:
                    errors.append(f"candidate {model_id!r} has invalid qualification status")
                qualification_ref = candidate.get("qualification_ref")
                if qualification == "qualified":
                    record = qualifications.get(qualification_ref) if isinstance(qualification_ref, str) else None
                    if not isinstance(record, dict):
                        errors.append(f"qualified candidate {model_id!r} has no attributable qualification record")
                    else:
                        expected = {
                            "status": "qualified",
                            "provider": "openai",
                            "model": model_id,
                            "capability": capability,
                        }
                        if any(record.get(key) != value for key, value in expected.items()):
                            errors.append(f"candidate {model_id!r} qualification record does not match its identity")
                        for field in (
                            "adapter_version",
                            "prompt_contract_version",
                            "measurement_run_id",
                            "reviewed_at",
                        ):
                            if not record.get(field):
                                errors.append(f"candidate {model_id!r} qualification record lacks {field}")
                elif qualification_ref is not None:
                    errors.append(f"unqualified candidate {model_id!r} cannot cite a qualification record")
                efforts = candidate.get("reasoning_efforts", [])
                if not isinstance(efforts, list) or any(item not in REASONING_EFFORTS for item in efforts):
                    errors.append(f"candidate {model_id!r} has invalid reasoning_efforts")
            if default_model not in candidate_ids:
                errors.append(f"capability {capability!r} default_model is not a candidate")
            default_effort = contract.get("default_reasoning_effort")
            if default_effort is not None:
                selected: dict[str, Any] = next(
                    (item for item in candidates if item.get("model") == default_model),
                    {},
                )
                if default_effort not in selected.get("reasoning_efforts", []):
                    errors.append(f"capability {capability!r} default reasoning effort is unsupported")

    review = profile.get("review")
    if profile.get("status") == "reviewed":
        if not isinstance(review, dict) or review.get("status") != "reviewed":
            errors.append("reviewed model profile lacks a reviewed record")
        elif not review.get("reviewers") or not review.get("reviewed_at"):
            errors.append("reviewed model profile lacks reviewers or review date")
    return sorted(set(errors))


def load_model_profile(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        resource = files("agent_doctor").joinpath("data/profiles/openai-model-capabilities-2026-08-17.json")
        profile = json.loads(resource.read_text(encoding="utf-8"))
    else:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ModelProfileError("model profile must be an object")
    errors = validate_model_profile(profile)
    if errors:
        raise ModelProfileError("; ".join(errors))
    return profile


def parse_available_models(payload: Any) -> frozenset[str]:
    """Parse the IDs from a saved GET /v1/models response.

    The returned set proves only account-visible availability.  It contains no
    ranking or capability conclusion.
    """

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ModelProfileError("available-models payload must contain a data array")
    identifiers: set[str] = set()
    for index, item in enumerate(payload["data"]):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ModelProfileError(f"available-models data[{index}] has no model id")
        identifiers.add(item["id"])
    return frozenset(identifiers)


def _refusal(
    profile: Mapping[str, Any],
    request: ModelSelectionRequest,
    *,
    code: str,
    reason: str,
) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "outcome": "not_selected",
        "code": code,
        "reason": reason,
        "provider": "openai",
        "capability": request.capability,
        "strategy": request.strategy,
        "profile": {
            "profile_id": profile.get("profile_id"),
            "profile_version": profile.get("profile_version"),
            "status": profile.get("status"),
        },
        "selected_model": None,
        "reasoning_effort": None,
        "availability": "not_evaluated",
        "availability_basis": request.availability_basis,
        "qualification": "not_evaluated",
        "invocation_ready": False,
        "blockers": [code],
    }
    decision["decision_id"] = stable_id("model-decision", decision)
    decision["selection_digest"] = digest(decision)
    return decision


def resolve_model(
    profile: Mapping[str, Any],
    request: ModelSelectionRequest,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Resolve a model without network access or an implicit fallback."""

    errors = validate_model_profile(profile)
    if errors:
        raise ModelProfileError("; ".join(errors))
    if request.strategy not in SELECTION_STRATEGIES:
        return _refusal(profile, request, code="invalid_strategy", reason="selection strategy must be auto or pinned")
    if request.reasoning_effort is not None and request.reasoning_effort not in REASONING_EFFORTS:
        return _refusal(profile, request, code="invalid_reasoning_effort", reason="reasoning effort is not in the closed vocabulary")
    if profile.get("status") != "reviewed":
        return _refusal(profile, request, code="profile_not_reviewed", reason="auto selection requires a reviewed profile")

    observed_date = as_of or date.today()
    review_after = date.fromisoformat(str(profile["review_after"]))
    if observed_date > review_after:
        return _refusal(
            profile,
            request,
            code="profile_stale",
            reason=f"profile review deadline {review_after.isoformat()} has passed",
        )

    capabilities = profile["capabilities"]
    if request.capability not in capabilities:
        return _refusal(profile, request, code="unknown_capability", reason="the reviewed profile does not define this capability")
    contract = capabilities[request.capability]
    if request.strategy == "pinned":
        if not request.requested_model:
            return _refusal(profile, request, code="pinned_model_required", reason="pinned strategy requires an exact model id")
        selected_model = request.requested_model
        selection_source = "user_pin"
    else:
        if request.requested_model:
            return _refusal(profile, request, code="auto_model_override", reason="use pinned strategy when specifying an exact model")
        selected_model = contract["default_model"]
        selection_source = "reviewed_profile_default"

    candidate = next((item for item in contract["candidates"] if item["model"] == selected_model), None)
    if candidate is None:
        return _refusal(
            profile,
            request,
            code="model_not_reviewed_for_capability",
            reason="the exact model is not reviewed for the requested capability",
        )

    supported_efforts = candidate.get("reasoning_efforts", [])
    default_effort = contract.get("default_reasoning_effort")
    selected_effort = request.reasoning_effort if request.reasoning_effort is not None else default_effort
    if selected_effort is not None and selected_effort not in supported_efforts:
        return _refusal(
            profile,
            request,
            code="unsupported_reasoning_effort",
            reason="the selected model does not support the requested reasoning effort",
        )
    if selected_effort is not None and not supported_efforts:
        return _refusal(
            profile,
            request,
            code="reasoning_effort_not_applicable",
            reason="reasoning effort is not applicable to this capability",
        )

    if request.available_models is None:
        availability = "unverified"
        availability_digest = None
    else:
        availability = "available" if selected_model in request.available_models else "unavailable"
        availability_digest = digest(sorted(request.available_models))

    qualification = candidate["qualification"]
    blockers: list[str] = []
    if availability == "unverified":
        blockers.append("account_availability_unverified")
    elif availability == "unavailable":
        blockers.append("model_unavailable_to_account")
    if request.require_qualified and qualification != "qualified":
        blockers.append("model_not_qualified_for_product_semantics")

    invocation_ready = not blockers
    decision = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "outcome": "selected",
        "code": "selected" if invocation_ready else "selected_with_gaps",
        "reason": "model resolved from a reviewed capability profile without implicit substitution",
        "provider": "openai",
        "capability": request.capability,
        "strategy": request.strategy,
        "selection_source": selection_source,
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
            "captured_at": profile["captured_at"],
            "review_after": profile["review_after"],
            "status": profile["status"],
        },
        "selected_model": selected_model,
        "reasoning_effort": selected_effort,
        "availability": availability,
        "availability_basis": request.availability_basis,
        "availability_snapshot_digest": availability_digest,
        "availability_proves_ranking": False,
        "qualification": qualification,
        "qualification_ref": candidate.get("qualification_ref"),
        "qualification_required": request.require_qualified,
        "invocation_ready": invocation_ready,
        "blockers": blockers,
        "source_refs": candidate["source_refs"],
        "fallback_used": False,
    }
    decision["decision_id"] = stable_id("model-decision", decision)
    decision["selection_digest"] = digest(decision)
    return decision


def fetch_official_markdown(uri: str) -> bytes:
    """Fetch one allowlisted official Markdown source with a strict size cap."""

    if not _is_official_uri(uri) or not uri.endswith(".md"):
        raise ModelProfileError("official source must be an allowlisted HTTPS Markdown URL")
    request = Request(uri, headers={"User-Agent": "agent-doctor-model-profile-watch/0.1"})
    try:
        opener = build_opener(_OfficialRedirectHandler())
        with opener.open(request, timeout=20) as response:
            final_uri = response.geturl()
            if not _is_official_uri(final_uri):
                raise ModelProfileError("official source redirected outside the allowlist")
            content_type = response.headers.get_content_type()
            if content_type not in {"text/markdown", "text/plain"}:
                raise ModelProfileError(f"official source returned unsupported content type {content_type!r}")
            body = response.read(MAX_OFFICIAL_DOCUMENT_BYTES + 1)
    except URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
        body = _fetch_official_markdown_with_curl(uri)
    if len(body) > MAX_OFFICIAL_DOCUMENT_BYTES:
        raise ModelProfileError("official source exceeded the documentation size limit")
    return body


def _fetch_official_markdown_with_curl(uri: str) -> bytes:
    """Use the system trust store when framework Python lacks CA certificates."""

    with tempfile.NamedTemporaryFile(prefix="agent-doctor-openai-doc-", suffix=".md") as handle:
        completed = subprocess.run(
            [
                "curl",
                "--proto",
                "=https",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "20",
                "--max-filesize",
                str(MAX_OFFICIAL_DOCUMENT_BYTES),
                "--user-agent",
                "agent-doctor-model-profile-watch/0.1",
                "--output",
                handle.name,
                "--write-out",
                "%{content_type}",
                uri,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
        if completed.returncode != 0:
            raise ModelProfileError("official source fetch failed with both Python and system trust stores")
        content_type = completed.stdout.split(";", 1)[0].strip()
        if content_type not in {"text/markdown", "text/plain"}:
            raise ModelProfileError(f"official source returned unsupported content type {content_type!r}")
        handle.seek(0)
        body = handle.read(MAX_OFFICIAL_DOCUMENT_BYTES + 1)
    return body


def _extract_watch_value(body: bytes, watch: Mapping[str, Any]) -> dict[str, Any]:
    text = body.decode("utf-8", errors="strict")
    kind = watch.get("kind")
    if kind == "latest_model":
        frontmatter = text[:2000]
        match = re.search(r"(?m)^\s*model:\s*([a-z0-9._-]+)\s*$", frontmatter)
        if match is None:
            raise ModelProfileError("latest-model source has no machine-readable model field")
        return {"latest_model": match.group(1)}
    if kind == "model_page":
        match = re.search(r"(?m)^Model ID:\s*`([^`]+)`\s*$", text[:5000])
        if match is None:
            raise ModelProfileError("model page has no Model ID field")
        return {"model_id": match.group(1)}
    if kind == "model_catalog":
        required = watch.get("required_model_ids", [])
        missing = [model for model in required if f"/{model}.md" not in text and f"`{model}`" not in text]
        return {"required_model_ids": list(required), "missing_model_ids": missing}
    if kind == "models_api":
        return {"list_models_documented": "**get** `/models`" in text}
    raise ModelProfileError("unsupported official-source watch contract")


def check_official_model_profile(
    profile: Mapping[str, Any],
    *,
    fetcher: Callable[[str], bytes] = fetch_official_markdown,
) -> dict[str, Any]:
    """Compare reviewed source digests and machine-readable facts.

    The report is a drift detector.  It never rewrites or promotes the profile.
    """

    errors = validate_model_profile(profile)
    if errors:
        return {
            "schema_version": DOC_CHECK_SCHEMA_VERSION,
            "outcome": "execution_failed",
            "profile_id": profile.get("profile_id"),
            "observations": [],
            "changes": [],
            "errors": errors,
            "automatic_promotion": False,
        }

    observations: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    fetch_errors: list[dict[str, str]] = []
    latest_candidate: str | None = None
    for source in profile["provenance"]:
        try:
            body = fetcher(source["uri"])
            actual_digest = content_digest(body)
            extracted = _extract_watch_value(body, source["watch"])
            observation = {
                "source_id": source["source_id"],
                "uri": source["uri"],
                "expected_digest": source["content_digest"],
                "actual_digest": actual_digest,
                "extracted": extracted,
            }
            observations.append(observation)
            if actual_digest != source["content_digest"]:
                changes.append({"source_id": source["source_id"], "kind": "content_digest_changed"})
            watch = source["watch"]
            if watch["kind"] == "latest_model":
                latest_candidate = extracted["latest_model"]
                if latest_candidate != watch.get("expected_model"):
                    changes.append(
                        {
                            "source_id": source["source_id"],
                            "kind": "latest_model_changed",
                            "expected": watch.get("expected_model"),
                            "observed": latest_candidate,
                        }
                    )
            elif watch["kind"] == "model_page" and extracted["model_id"] != watch.get("expected_model_id"):
                changes.append(
                    {
                        "source_id": source["source_id"],
                        "kind": "model_id_changed",
                        "expected": watch.get("expected_model_id"),
                        "observed": extracted["model_id"],
                    }
                )
            elif watch["kind"] == "model_catalog" and extracted["missing_model_ids"]:
                changes.append(
                    {
                        "source_id": source["source_id"],
                        "kind": "required_models_missing_from_catalog",
                        "models": extracted["missing_model_ids"],
                    }
                )
            elif watch["kind"] == "models_api" and not extracted["list_models_documented"]:
                changes.append({"source_id": source["source_id"], "kind": "models_api_contract_changed"})
        except Exception as exc:  # explicit network/parser boundary
            fetch_errors.append({"source_id": source["source_id"], "error": type(exc).__name__})

    if fetch_errors:
        outcome = "execution_failed"
    elif changes:
        outcome = "candidate_change"
    else:
        outcome = "current"
    report = {
        "schema_version": DOC_CHECK_SCHEMA_VERSION,
        "outcome": outcome,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "observations": sorted(observations, key=lambda item: item["source_id"]),
        "changes": sorted(changes, key=lambda item: (item["source_id"], item["kind"])),
        "errors": sorted(fetch_errors, key=lambda item: item["source_id"]),
        "latest_model_candidate": latest_candidate,
        "automatic_promotion": False,
        "next_step": "review source diffs, run routing and semantic qualification, then promote by reviewed pull request",
    }
    report["report_id"] = stable_id("model-doc-check", report)
    return report


def _subset_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _subset_matches(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return actual == expected
    return actual == expected


def validate_model_routing_suite(suite: Any, schema: Mapping[str, Any]) -> list[SchemaError]:
    errors = validate(suite, dict(schema))
    if isinstance(suite, dict) and isinstance(suite.get("cases"), list):
        identifiers = [item.get("id") for item in suite["cases"] if isinstance(item, dict)]
        if len(identifiers) != len(set(identifiers)):
            errors.append(SchemaError("$.cases", "model-routing scenario identifiers must be unique"))
    return sorted(errors, key=lambda item: (item.path, item.message))


def run_model_routing_suite(
    suite: Mapping[str, Any],
    schema: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validation_errors = validate_model_routing_suite(suite, schema)
    if validation_errors:
        return {
            "schema_version": "agent-doctor-model-routing-test-run/0.1",
            "suite_id": suite.get("suite_id"),
            "evidence_outcome": "execution_failed",
            "gate_outcome": "not_evaluated",
            "counts": {"passed": 0, "failed": 0, "invalid": len(validation_errors)},
            "validation_errors": [{"path": item.path, "message": item.message} for item in validation_errors],
            "cases": [],
            "measurement_status": "not_performed",
        }

    records: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    for case in suite["cases"]:
        request_data = case["request"]
        available = request_data.get("available_models")
        request = ModelSelectionRequest(
            capability=request_data["capability"],
            strategy=request_data.get("strategy", "auto"),
            requested_model=request_data.get("requested_model"),
            reasoning_effort=request_data.get("reasoning_effort"),
            available_models=frozenset(available) if available is not None else None,
            require_qualified=bool(request_data.get("require_qualified", False)),
        )
        decision = resolve_model(profile, request, as_of=date.fromisoformat(case["as_of"]))
        matches = _subset_matches(decision, case["expected"])
        records.append(
            {
                "id": case["id"],
                "status": "passed" if matches else "failed",
                "expected": case["expected"],
                "actual": decision,
            }
        )
        if matches:
            passed += 1
        else:
            failed += 1
    return {
        "schema_version": "agent-doctor-model-routing-test-run/0.1",
        "suite_id": suite["suite_id"],
        "suite_version": suite["suite_version"],
        "evidence_outcome": "valid",
        "gate_outcome": "satisfied_for_executed_scenarios" if not failed else "policy_failed",
        "counts": {"passed": passed, "failed": failed, "invalid": 0},
        "validation_errors": [],
        "cases": records,
        "measurement_status": "not_performed",
        "measurement_note": "Routing contract regression is not provider quality or product semantic qualification.",
    }
