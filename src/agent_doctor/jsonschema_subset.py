"""Small, deterministic JSON Schema 2020-12 subset used by local artifacts.

The project runtime intentionally has no third-party dependencies.  The
published schemas use a deliberately small keyword set; this validator rejects
unknown behavior by implementing exactly that set instead of silently treating
schema validation as optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .canonical import canonical_json


@dataclass(frozen=True)
class SchemaError:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _resolve_pointer(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local JSON pointers are supported: {reference}")
    current: Any = root
    for encoded in reference[2:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"unresolvable local JSON pointer: {reference}")
        current = current[token]
    if not isinstance(current, dict):
        raise ValueError(f"schema reference does not identify an object: {reference}")
    return current


def validate(instance: Any, schema: dict[str, Any]) -> list[SchemaError]:
    """Return every validation error in deterministic path order."""

    errors: list[SchemaError] = []

    def fail(path: str, message: str) -> None:
        errors.append(SchemaError(path, message))

    def visit(value: Any, rule: dict[str, Any], path: str) -> None:
        if "$ref" in rule:
            try:
                target = _resolve_pointer(schema, str(rule["$ref"]))
            except ValueError as exc:
                fail(path, str(exc))
                return
            visit(value, target, path)
            return

        expected = rule.get("type")
        if expected is not None:
            accepted = [expected] if isinstance(expected, str) else list(expected)
            if not any(_json_type_matches(value, item) for item in accepted):
                fail(path, f"expected type {' or '.join(accepted)}, got {type(value).__name__}")
                return

        if "const" in rule and value != rule["const"]:
            fail(path, f"must equal {rule['const']!r}")
        if "enum" in rule and value not in rule["enum"]:
            fail(path, f"must be one of {rule['enum']!r}")

        if isinstance(value, str):
            if len(value) < int(rule.get("minLength", 0)):
                fail(path, f"must have at least {rule['minLength']} characters")
            if "pattern" in rule and re.search(str(rule["pattern"]), value) is None:
                fail(path, f"does not match {rule['pattern']!r}")
            if rule.get("format") == "date":
                try:
                    parsed = date.fromisoformat(value)
                    if parsed.isoformat() != value:
                        raise ValueError
                except ValueError:
                    fail(path, "must be an RFC 3339 full-date")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                fail(path, f"must be at least {rule['minimum']}")

        if isinstance(value, list):
            if len(value) < int(rule.get("minItems", 0)):
                fail(path, f"must contain at least {rule['minItems']} item(s)")
            if rule.get("uniqueItems"):
                serialized = [canonical_json(item) for item in value]
                if len(serialized) != len(set(serialized)):
                    fail(path, "items must be unique")
            item_rule = rule.get("items")
            if isinstance(item_rule, dict):
                for index, item in enumerate(value):
                    visit(item, item_rule, f"{path}[{index}]")

        if isinstance(value, dict):
            required = rule.get("required", [])
            for key in required:
                if key not in value:
                    fail(path, f"missing required property {key!r}")
            properties = rule.get("properties", {})
            for key, child in properties.items():
                if key in value and isinstance(child, dict):
                    visit(value[key], child, f"{path}.{key}")
            additional = rule.get("additionalProperties", True)
            for key in value:
                if key in properties:
                    continue
                if additional is False:
                    fail(f"{path}.{key}", "additional property is not allowed")
                elif isinstance(additional, dict):
                    visit(value[key], additional, f"{path}.{key}")

    visit(instance, schema, "$")
    return sorted(errors, key=lambda item: (item.path, item.message))
