"""Published result-schema loading and combined structural/semantic checks."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .invariants import InvariantError, validate_result_graph
from .jsonschema_subset import SchemaError, validate


def load_result_schema() -> dict[str, Any]:
    resource = files("agent_doctor").joinpath("data/schema/result.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_result(graph: dict[str, Any], *, require_sealed: bool = True) -> list[SchemaError | InvariantError]:
    structural = validate(graph, load_result_schema())
    semantic = validate_result_graph(graph, require_sealed=require_sealed)
    return [*structural, *semantic]
