from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import TypeAdapter

from posokanei import (
    CategoryTree,
    Competitors,
    PriceDrop,
    Product,
    ProductPage,
    Stats,
)
from posokanei.models import RetailerList
from tests.contract import load_fixture


def test_retailers() -> None:
    parsed = RetailerList.model_validate(load_fixture("meta_retailers.json"))
    assert parsed.count == len(parsed.retailers) == 23
    greek = {retailer.id for retailer in parsed.retailers if retailer.country == "GR"}
    assert len(greek) == 11
    assert {"sklavenitis", "ab_vasilopoulos", "lidl", "masoutis"} <= greek


def test_category_tree_is_recursive() -> None:
    tree = CategoryTree.model_validate(load_fixture("meta_categories_tree.json"))
    assert tree.total_categories == 2694
    root = tree.tree[0]
    assert root.depth == 0
    assert root.name_en == "Infants"
    assert root.children[0].depth == 1
    assert root.effective_vat_rates["GR"].rate == 24.0


def test_product_page() -> None:
    page = ProductPage.model_validate(load_fixture("products_list.json"))
    assert (page.total, page.page, page.page_size, page.total_pages) == (307, 1, 36, 9)
    assert page.has_next
    assert not page.has_prev
    assert len(page.products) == 36
    assert all(product.history is None for product in page.products)
    dropped = [product for product in page.products if product.price_drop]
    assert isinstance(dropped[0].price_drop_start, date)


def test_product_detail() -> None:
    product = Product.model_validate(load_fixture("product_detail.json"))
    assert product.id == "975c34c8d04740dda1e28cd51e28e283"
    assert product.unit == "kg"
    assert product.unit_quantity == 0.72
    assert isinstance(product.updated_at, datetime)
    assert len(product.retailer_prices) == 8
    assert "sklavenitis" in {price.retailer for price in product.retailer_prices}
    assert product.price_stats is not None
    assert product.price_stats.retailer_count == 8
    assert product.history is None


def test_product_detail_with_description() -> None:
    product = Product.model_validate(load_fixture("product_detail_2.json"))
    assert isinstance(product.description, str)


def test_product_history() -> None:
    product = Product.model_validate(load_fixture("product_history.json"))
    history = product.history
    assert history is not None
    assert history.date_range.start == date(2026, 8, 12)
    assert set(history.daily_prices) == set(history.retailers)
    first = history.daily_prices["sklavenitis"][0]
    assert first.date == date(2026, 8, 12)
    assert first.price > 0


def test_product_without_prices() -> None:
    product = Product.model_validate(load_fixture("product_by_barcode.json"))
    assert product.price_stats is None
    assert product.image_url is None
    assert product.retailer_prices == []


def test_search_page() -> None:
    page = ProductPage.model_validate(load_fixture("products_search.json"))
    assert page.total == 280
    assert len(page.products) == page.page_size == 5


def test_price_drops() -> None:
    drops = TypeAdapter(list[PriceDrop]).validate_python(load_fixture("products_price_drop.json"))
    assert len(drops) == 40
    assert drops[0].price_drop_start == date(2026, 8, 31)
    assert drops[-1].price_drop_start is None


def test_competitors() -> None:
    parsed = Competitors.model_validate(load_fixture("product_competitors.json"))
    assert parsed.total_competitors == 51
    priced = [c for c in parsed.competitors if c.retailer_prices]
    assert {price.retailer for c in priced for price in c.retailer_prices} == {"sklavenitis"}
    assert any(c.price_stats is None for c in parsed.competitors)


def test_stats() -> None:
    stats = Stats.model_validate(load_fixture("meta_stats.json"))
    assert stats.retailer_count == len(stats.retailers) == 23
    assert stats.total_products == 10150


@pytest.mark.parametrize("name", ["meta_stats.json", "product_detail.json"])
def test_an_unknown_field_is_kept_not_refused(name: str) -> None:
    payload = load_fixture(name)
    payload["brand_new_field"] = "x"
    model = Stats if name == "meta_stats.json" else Product
    parsed = model.model_validate(payload)
    assert parsed.model_extra == {"brand_new_field": "x"}
