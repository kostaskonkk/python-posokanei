from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from tests.contract import FIXTURE_SCHEMAS, FIXTURES, load_fixture, spec, violations


def test_every_fixture_has_a_schema() -> None:
    assert {path.name for path in FIXTURES.glob("*.json")} == set(FIXTURE_SCHEMAS)


def test_component_schemas_are_valid_json_schema() -> None:
    for schema in spec()["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_fixture_fits_the_spec_with_no_unknown_field(name: str) -> None:
    assert violations(load_fixture(name), FIXTURE_SCHEMAS[name]) == []


def test_an_unknown_field_is_a_violation() -> None:
    payload = load_fixture("meta_stats.json")
    payload["brand_new_field"] = 1
    found = violations(payload, FIXTURE_SCHEMAS["meta_stats.json"])
    assert len(found) == 1
    assert "brand_new_field" in found[0]


def test_a_nested_unknown_field_is_a_violation() -> None:
    payload = load_fixture("product_detail.json")
    payload["retailer_prices"][0]["loyalty_price"] = 1.0
    found = violations(payload, FIXTURE_SCHEMAS["product_detail.json"])
    assert any("loyalty_price" in line for line in found)


def test_a_wrong_type_is_a_violation() -> None:
    payload = load_fixture("meta_stats.json")
    payload["total_products"] = "many"
    assert violations(payload, FIXTURE_SCHEMAS["meta_stats.json"])
