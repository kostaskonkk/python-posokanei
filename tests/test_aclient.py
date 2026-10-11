"""The async client against a mocked API. It shares its requests and its reading of answers with
the sync client (`_request.py`), so this covers the calls and the waiting, not every case again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from posokanei import (
    AsyncPosoKanei,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SchemaError,
)
from posokanei._ratelimit import AsyncRateLimiter
from tests.contract import load_fixture

BASE = "https://api.posokanei.gov.gr"
PRODUCT_ID = "975c34c8d04740dda1e28cd51e28e283"


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def waits() -> list[float]:
    return []


@pytest.fixture
async def pk(api: respx.MockRouter, waits: list[float]) -> AsyncIterator[AsyncPosoKanei]:
    """A client that does not really wait: what it would have slept is in `waits`."""

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    async with AsyncPosoKanei(min_interval=0) as client:
        client._sleep = sleep
        yield client


def page(number: int, has_next: bool) -> dict[str, Any]:
    payload: dict[str, Any] = load_fixture("products_list.json")
    payload.update(page=number, has_next=has_next, has_prev=number > 1)
    payload["products"] = payload["products"][:2]
    return payload


async def test_sends_the_web_apps_headers(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    await pk.stats()
    headers = route.calls.last.request.headers
    assert headers["Origin"] == "https://posokanei.gov.gr"
    assert headers["Referer"] == "https://posokanei.gov.gr/"
    assert headers["X-Platform"] == "flutter-web"
    assert headers["X-App-Version"] == "1.0.0"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("Mozilla/5.0")


async def test_retailers_are_filtered_by_country_here(
    api: respx.MockRouter, pk: AsyncPosoKanei
) -> None:
    route = api.get("/meta/retailers").respond(json=load_fixture("meta_retailers.json"))
    greek = await pk.retailers()
    assert dict(route.calls.last.request.url.params) == {"countries": "GR"}
    assert len(greek) == 11
    assert {retailer.country for retailer in greek} == {"GR"}
    assert len(await pk.retailers(country="all")) == 23


async def test_categories_sends_bools_as_words(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/meta/categories/tree").respond(json=load_fixture("meta_categories_tree.json"))
    tree = await pk.categories(include_hidden=True)
    assert dict(route.calls.last.request.url.params) == {
        "include_counts": "true",
        "include_hidden": "true",
    }
    assert tree.root_count == 19


async def test_products_maps_its_arguments(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/products").respond(json=load_fixture("products_list.json"))
    result = await pk.products("abc", page=2, sort_order="desc")
    assert dict(route.calls.last.request.url.params) == {
        "category": "abc",
        "countries": "GR",
        "page": "2",
        "page_size": "36",
        "sort_by": "unit_price",
        "sort_order": "desc",
    }
    assert len(result.products) == 36
    await pk.products("abc", is_international=False)
    assert route.calls.last.request.url.params["is_international"] == "false"


async def test_iter_products_follows_has_next(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/products").mock(
        side_effect=[
            httpx.Response(200, json=page(1, True)),
            httpx.Response(200, json=page(2, True)),
            httpx.Response(200, json=page(3, False)),
        ]
    )
    products = [item async for item in pk.aiter_products("abc")]
    assert len(products) == 6
    assert [call.request.url.params["page"] for call in route.calls] == ["1", "2", "3"]


async def test_iter_products_stops_at_an_empty_page(
    api: respx.MockRouter, pk: AsyncPosoKanei
) -> None:
    empty = page(1, True)
    empty["products"] = []
    route = api.get("/products").respond(json=empty)
    assert [item async for item in pk.aiter_products("abc")] == []
    assert route.call_count == 1


async def test_product(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get(f"/products/{PRODUCT_ID}").respond(json=load_fixture("product_history.json"))
    product = await pk.product(PRODUCT_ID, history=True)
    assert dict(route.calls.last.request.url.params) == {
        "countries": "all",
        "include_tax": "true",
        "sort_retailers": "asc",
        "include_history": "true",
        "price_type": "unit_price",
    }
    assert product.history is not None


async def test_search_posts_a_json_body(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.post("/products/search").respond(json=load_fixture("products_search.json"))
    result = await pk.search("γάλα", page_size=5, sort_order="asc", ids=["a"])
    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/json"
    assert httpx.Response(200, content=request.content).json() == {
        "title": "γάλα",
        "page": 1,
        "page_size": 5,
        "sort_order": "asc",
        "ids": ["a"],
    }
    assert result.total == 280


async def test_by_barcode(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/products/barcode/123").respond(json=load_fixture("product_by_barcode.json"))
    product = await pk.by_barcode("123")
    assert product is not None
    assert dict(route.calls.last.request.url.params) == {"countries": "GR", "include_tax": "true"}


async def test_by_barcode_is_none_on_404(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    api.get("/products/barcode/404").respond(404, json={"detail": "Not found"})
    assert await pk.by_barcode("404") is None


async def test_price_drops(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    api.get("/products/price-drop").respond(json=load_fixture("products_price_drop.json"))
    assert len(await pk.price_drops()) == 40


async def test_competitors(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get(f"/products/{PRODUCT_ID}/competitors").respond(
        json=load_fixture("product_competitors.json")
    )
    result = await pk.competitors(PRODUCT_ID, retailer="sklavenitis")
    assert dict(route.calls.last.request.url.params) == {
        "retailer": "sklavenitis",
        "include_tax": "true",
    }
    assert result.id == PRODUCT_ID


async def test_404_is_not_found(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    api.get("/products/nope").respond(404, json={"detail": "Not found"})
    with pytest.raises(NotFoundError) as caught:
        await pk.product("nope")
    assert caught.value.status_code == 404
    assert "Not found" in caught.value.body


async def test_403_says_what_to_check(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/meta/stats").respond(403, text="403 Forbidden")
    with pytest.raises(ForbiddenError, match="User-Agent"):
        await pk.stats()
    assert route.call_count == 1  # never tried again


async def test_a_payload_that_does_not_fit_is_a_schema_error(
    api: respx.MockRouter, pk: AsyncPosoKanei
) -> None:
    api.get("/meta/stats").respond(json={"total_products": "many"})
    with pytest.raises(SchemaError) as caught:
        await pk.stats()
    assert caught.value.payload == {"total_products": "many"}
    assert caught.value.model == "Stats"
    api.get("/products/price-drop").respond(json={"not": "a list"})
    with pytest.raises(SchemaError):
        await pk.price_drops()


async def test_429_then_success(
    api: respx.MockRouter, pk: AsyncPosoKanei, waits: list[float]
) -> None:
    route = api.get("/meta/stats").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json=load_fixture("meta_stats.json")),
        ]
    )
    assert (await pk.stats()).retailer_count == 23
    assert route.call_count == 3
    assert len(waits) == 2
    assert 0.25 <= waits[0] <= 0.5  # half a second, less up to half of it
    assert 0.5 <= waits[1] <= 1.0  # doubled


async def test_a_long_retry_after_is_not_slept_on(
    api: respx.MockRouter, pk: AsyncPosoKanei, waits: list[float]
) -> None:
    route = api.get("/products/barcode/1").respond(
        429, headers={"Retry-After": "803"}, json={"detail": "Too many barcode search requests."}
    )
    with pytest.raises(RateLimitError, match="retry after 803s") as caught:
        await pk.by_barcode("1")
    assert caught.value.retry_after == 803.0
    assert route.call_count == 1
    assert waits == []


async def test_429_every_time_is_a_rate_limit_error(
    api: respx.MockRouter, pk: AsyncPosoKanei, waits: list[float]
) -> None:
    route = api.get("/meta/stats").respond(429)
    with pytest.raises(RateLimitError):
        await pk.stats()
    assert route.call_count == 4  # the first try and max_retries=3 more
    assert len(waits) == 3


async def test_a_cache_hit_makes_no_request(api: respx.MockRouter, pk: AsyncPosoKanei) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    first = await pk.stats()
    second = await pk.stats()
    assert route.call_count == 1
    assert first == second
    assert first is not second  # parsed afresh, so changing one does not change the other


async def test_requests_are_spaced(api: respx.MockRouter) -> None:
    api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    api.get("/products/price-drop").respond(json=[])
    now = [100.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    async with AsyncPosoKanei(min_interval=0.25) as client:
        client._limiter = AsyncRateLimiter(0.25, clock=lambda: now[0], sleep=sleep)
        await client.stats()
        await client.stats()  # from the cache: no wait
        assert slept == []
        now[0] += 0.1
        await client.price_drops()
        assert slept == [pytest.approx(0.15)]


async def test_an_http_client_of_your_own_is_not_closed(api: respx.MockRouter) -> None:
    api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    async with httpx.AsyncClient() as http:
        async with AsyncPosoKanei(http_client=http, min_interval=0) as client:
            await client.stats()
        assert not http.is_closed


async def test_a_transport_can_be_passed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load_fixture("meta_stats.json"))

    async with AsyncPosoKanei(transport=httpx.MockTransport(handler), min_interval=0) as client:
        assert (await client.stats()).total_products == 10150
