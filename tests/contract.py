"""The spec as a strict contract: a payload must fit its schema and carry no field the spec does
not name. The models accept unknown fields so that users never break; this is where a new field
upstream is noticed instead."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "openapi.yaml"
FIXTURES = ROOT / "tests" / "fixtures"

# Each fixture, and the schema its payload must fit: a component's name, or a list of one.
FIXTURE_SCHEMAS: dict[str, dict[str, Any]] = {
    "meta_retailers.json": {"$ref": "#/components/schemas/RetailerList"},
    "meta_categories_tree.json": {"$ref": "#/components/schemas/CategoryTree"},
    "meta_stats.json": {"$ref": "#/components/schemas/Stats"},
    "products_list.json": {"$ref": "#/components/schemas/ProductPage"},
    "products_search.json": {"$ref": "#/components/schemas/ProductPage"},
    "product_detail.json": {"$ref": "#/components/schemas/Product"},
    "product_detail_2.json": {"$ref": "#/components/schemas/Product"},
    "product_history.json": {"$ref": "#/components/schemas/Product"},
    "product_by_barcode.json": {"$ref": "#/components/schemas/Product"},
    "product_competitors.json": {"$ref": "#/components/schemas/Competitors"},
    "products_price_drop.json": {
        "type": "array",
        "items": {"$ref": "#/components/schemas/PriceDrop"},
    },
}


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@cache
def spec() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    return loaded


def _close(schema: Any) -> None:
    """Forbid unknown fields on every object schema that names its fields."""
    if isinstance(schema, dict):
        if "properties" in schema and "additionalProperties" not in schema:
            schema["additionalProperties"] = False
        for value in schema.values():
            _close(value)
    elif isinstance(schema, list):
        for value in schema:
            _close(value)


@cache
def _strict_components() -> dict[str, Any]:
    components: dict[str, Any] = copy.deepcopy(spec()["components"])
    _close(components["schemas"])
    return components


def violations(payload: Any, schema: dict[str, Any]) -> list[str]:
    """Where `payload` breaks `schema` (which may `$ref` the spec's components), as lines of
    `path: message`. Empty when it fits."""
    document = {**schema, "components": _strict_components()}
    errors = Draft202012Validator(document).iter_errors(payload)
    return sorted(
        f"{'/'.join(str(part) for part in error.path)}: {error.message}" for error in errors
    )
