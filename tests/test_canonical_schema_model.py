from __future__ import annotations

import copy

from agent_doctor.canonical import canonical_json, digest, stable_id
from agent_doctor.jsonschema_subset import validate
from agent_doctor.schema import load_result_schema


def test_canonical_json_and_ids_ignore_mapping_order() -> None:
    left = {"b": [2, 1], "a": {"x": True}}
    right = {"a": {"x": True}, "b": [2, 1]}
    assert canonical_json(left) == canonical_json(right)
    assert digest(left) == digest(right)
    assert stable_id("case", left) == stable_id("case", right)


def test_schema_subset_rejects_extra_properties_and_duplicate_items() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["values"],
        "properties": {
            "values": {"type": "array", "uniqueItems": True, "items": {"type": "string"}}
        },
    }
    errors = validate({"values": ["a", "a"], "extra": True}, schema)
    assert {item.path for item in errors} == {"$.values", "$.extra"}


def test_published_result_schema_has_closed_product_axes() -> None:
    schema = load_result_schema()
    states = schema["$defs"]["state"]["enum"]
    labels = schema["$defs"]["label"]["enum"]
    assert "not_applicable" not in states
    assert "pass" not in labels
    assert "semantic_conflict" in labels
    assert schema["additionalProperties"] is False
