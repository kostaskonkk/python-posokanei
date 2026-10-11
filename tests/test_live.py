"""One call per endpoint on the real API. Run by hand, or on a schedule: `pytest -m live`.

Each test holds the raw answer against the spec with unknown fields forbidden, so this is where a
change upstream shows: a new field, a field gone, a type that moved. It makes about ten requests,
a second apart. With `--record` the answers are written to tests/fixtures/, cut down."""

from __future__ import annotations

from typing import Any

import pytest

from posokanei import CategoryNode, RateLimitError
from tests.conftest import Live

pytestmark = pytest.mark.live

# What the tests after the first learn from the API and pass on.
found: dict[str, str] = {}


def first_with_products(nodes: list[CategoryNode]) -> CategoryNode | None:
    for node in nodes:
        if not node.children and node.product_count > 0:
            return node
        below = first_with_products(node.children)
        if below is not None:
            return below
    return None


def test_retailers(live: Live) -> None:
    retailers = live.pk.retailers(country="all")
    live.check("meta_retailers.json")
    assert "sklavenitis" in {retailer.id for retailer in retailers}


def test_stats(live: Live) -> None:
    assert live.pk.stats().total_products > 0
    live.check("meta_stats.json")


def test_categories(live: Live) -> None:
    tree = live.pk.categories()

    def two_roots(payload: Any) -> Any:
        return {**payload, "tree": payload["tree"][:2]}

    live.check("meta_categories_tree.json", two_roots)
    leaf = first_with_products(tree.tree)
    assert leaf is not None, "no category has products"
    found["category"] = leaf.category_id


def test_products(live: Live) -> None:
    if "category" not in found:
        pytest.skip("needs the category tree")
    page = live.pk.products(found["category"])
    live.check("products_list.json")
    assert page.products
    priced = [product for product in page.products if product.retailers]
    found["product"] = priced[0].id
    found["retailer"] = priced[0].retailers[0]


def test_product(live: Live) -> None:
    if "product" not in found:
        pytest.skip("needs a product from the list")
    product = live.pk.product(found["product"])
    live.check("product_detail.json")
    assert product.id == found["product"]
    assert product.history is None


def test_product_history(live: Live) -> None:
    if "product" not in found:
        pytest.skip("needs a product from the list")
    product = live.pk.product(found["product"], history=True)
    live.check("product_history.json")
    assert product.history is not None
    assert product.history.daily_prices


def test_competitors(live: Live) -> None:
    if "product" not in found:
        pytest.skip("needs a product from the list")
    live.pk.competitors(found["product"], retailer=found["retailer"])

    def six(payload: Any) -> Any:
        priced = [item for item in payload["competitors"] if item["retailer_prices"]][:3]
        bare = [item for item in payload["competitors"] if not item["retailer_prices"]][:3]
        return {**payload, "competitors": priced + bare}

    live.check("product_competitors.json", six)


def test_search(live: Live) -> None:
    page = live.pk.search("γάλα", page_size=5)
    live.check("products_search.json")
    assert page.total > 0


def test_price_drops(live: Live) -> None:
    drops = live.pk.price_drops()

    def forty(payload: Any) -> Any:
        undated = [item for item in payload if item["price_drop_start"] is None][:2]
        return payload[: 40 - len(undated)] + undated

    live.check("products_price_drop.json", forty)
    assert drops


def test_by_barcode(live: Live) -> None:
    # A code the API knew on 2026-10-11. If it forgets it, the answer is None and nothing is held
    # against the spec. The endpoint has a limit of its own, a few requests in a quarter of an
    # hour: being over it says nothing about the API's shape.
    try:
        product = live.pk.by_barcode("0000000000000")
    except RateLimitError as error:
        pytest.skip(f"the barcode endpoint is rate limited: {error}")
    if product is None:
        pytest.skip("the API no longer knows this barcode")
    live.check("product_by_barcode.json")
