"""Versioned, attributable platform profiles and safe compatibility gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileDecision:
    usable: bool
    state: str
    reason: str


REQUIRED_PROFILE_FIELDS = {
    "profile_schema_version",
    "profile_id",
    "profile_version",
    "ecosystem",
    "status",
    "captured_at",
    "compatibility",
    "provenance",
    "rules",
    "review",
}


def validate_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_PROFILE_FIELDS - set(profile))
    if missing:
        errors.append(f"missing profile fields: {', '.join(missing)}")
    if profile.get("profile_schema_version") != "agent-doctor-platform-profile/0.1":
        errors.append("unsupported profile schema version")
    if profile.get("ecosystem") != "codex":
        errors.append("MVP only accepts Codex profiles")
    if profile.get("status") not in {"reviewed", "draft", "stale", "incompatible", "unknown"}:
        errors.append("unknown profile status")
    provenance = profile.get("provenance", [])
    if not provenance:
        errors.append("profile has no provenance")
    for index, source in enumerate(provenance):
        if not source.get("uri", "").startswith(("https://learn.chatgpt.com/", "https://developers.openai.com/")):
            errors.append(f"provenance[{index}] is not an official OpenAI documentation URI")
        if not source.get("assertions"):
            errors.append(f"provenance[{index}] has no reviewed assertions")
    review = profile.get("review", {})
    if profile.get("status") == "reviewed":
        if review.get("status") != "reviewed" or not review.get("reviewers") or not review.get("reviewed_at"):
            errors.append("reviewed profile lacks a complete review record")
    return errors


def compatibility_decision(profile: dict[str, Any], *, require_reviewed: bool = True) -> ProfileDecision:
    errors = validate_profile(profile)
    if errors:
        return ProfileDecision(False, "error", "; ".join(errors))
    status = profile["status"]
    if require_reviewed and status != "reviewed":
        if status in {"stale", "unknown", "draft"}:
            return ProfileDecision(False, "insufficient_evidence", f"platform profile is {status}")
        return ProfileDecision(False, "error", f"platform profile is {status}")
    compatibility = profile.get("compatibility", {})
    if compatibility.get("status") == "incompatible":
        return ProfileDecision(False, "error", "platform profile is incompatible")
    if compatibility.get("status") in {"unknown", "stale"}:
        return ProfileDecision(False, "insufficient_evidence", f"profile compatibility is {compatibility['status']}")
    return ProfileDecision(True, "compatible", "reviewed profile is compatible with its documented snapshot")


def load_profile(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        resource = files("agent_doctor").joinpath("data/profiles/codex-docs-2026-08-17.json")
        profile = json.loads(resource.read_text(encoding="utf-8"))
    else:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_profile(profile)
    if errors:
        raise ProfileError("; ".join(errors))
    return profile


def profile_rule(profile: dict[str, Any], dotted_path: str) -> Any:
    value: Any = profile.get("rules", {})
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ProfileError(f"profile rule is unknown: {dotted_path}")
        value = value[part]
    return value
