"""The sync client against a mocked API: what it sends, and what it does with each answer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from posokanei import (
    APIError,
    ForbiddenError,
    NotFoundError,
    PosoKanei,
    RateLimitError,
    SchemaError,
)
from posokanei._ratelimit import RateLimiter
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
def pk(api: respx.MockRouter, waits: list[float]) -> Iterator[PosoKanei]:
    """A client that does not really wait: what it would have slept is in `waits`."""
    with PosoKanei(min_interval=0) as client:
        client._sleep = waits.append
        yield client


def page(number: int, has_next: bool) -> dict[str, Any]:
    payload: dict[str, Any] = load_fixture("products_list.json")
    payload.update(page=number, has_next=has_next, has_prev=number > 1)
    payload["products"] = payload["products"][:2]
    return payload


def test_sends_the_web_apps_headers(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    pk.stats()
    headers = route.calls.last.request.headers
    assert headers["Origin"] == "https://posokanei.gov.gr"
    assert headers["Referer"] == "https://posokanei.gov.gr/"
    assert headers["X-Platform"] == "flutter-web"
    assert headers["X-App-Version"] == "1.0.0"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("Mozilla/5.0")


def test_user_agent_and_base_url_are_configurable() -> None:
    with respx.mock() as router:
        route = router.get("https://example.test/meta/stats").respond(
            json=load_fixture("meta_stats.json")
        )
        with PosoKanei(base_url="https://example.test/", user_agent="Mozilla/5.0 mine") as client:
            client.stats()
    assert route.calls.last.request.headers["User-Agent"] == "Mozilla/5.0 mine"


def test_retailers_are_filtered_by_country_here(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/meta/retailers").respond(json=load_fixture("meta_retailers.json"))
    greek = pk.retailers()
    assert dict(route.calls.last.request.url.params) == {"countries": "GR"}
    assert len(greek) == 11
    assert {retailer.country for retailer in greek} == {"GR"}
    assert len(pk.retailers(country="all")) == 23


def test_categories_sends_bools_as_words(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/meta/categories/tree").respond(json=load_fixture("meta_categories_tree.json"))
    tree = pk.categories(include_hidden=True)
    assert dict(route.calls.last.request.url.params) == {
        "include_counts": "true",
        "include_hidden": "true",
    }
    assert tree.root_count == 19


def test_products_maps_its_arguments(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/products").respond(json=load_fixture("products_list.json"))
    result = pk.products("abc", page=2, sort_order="desc")
    assert dict(route.calls.last.request.url.params) == {
        "category": "abc",
        "countries": "GR",
        "page": "2",
        "page_size": "36",
        "sort_by": "unit_price",
        "sort_order": "desc",
    }
    assert len(result.products) == 36
    pk.products("abc", is_international=False)
    assert route.calls.last.request.url.params["is_international"] == "false"


def test_iter_products_follows_has_next(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/products").mock(
        side_effect=[
            httpx.Response(200, json=page(1, True)),
            httpx.Response(200, json=page(2, True)),
            httpx.Response(200, json=page(3, False)),
        ]
    )
    products = list(pk.iter_products("abc"))
    assert len(products) == 6
    assert [call.request.url.params["page"] for call in route.calls] == ["1", "2", "3"]


def test_iter_products_stops_at_an_empty_page(api: respx.MockRouter, pk: PosoKanei) -> None:
    empty = page(1, True)
    empty["products"] = []
    route = api.get("/products").respond(json=empty)
    assert list(pk.iter_products("abc")) == []
    assert route.call_count == 1


def test_product(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get(f"/products/{PRODUCT_ID}").respond(json=load_fixture("product_history.json"))
    product = pk.product(PRODUCT_ID, history=True)
    assert dict(route.calls.last.request.url.params) == {
        "countries": "all",
        "include_tax": "true",
        "sort_retailers": "asc",
        "include_history": "true",
        "price_type": "unit_price",
    }
    assert product.history is not None


def test_search_posts_a_json_body(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.post("/products/search").respond(json=load_fixture("products_search.json"))
    result = pk.search("γάλα", page_size=5, sort_order="asc", ids=["a"])
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


def test_by_barcode(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/products/barcode/123").respond(json=load_fixture("product_by_barcode.json"))
    product = pk.by_barcode("123")
    assert product is not None
    assert dict(route.calls.last.request.url.params) == {"countries": "GR", "include_tax": "true"}


def test_by_barcode_is_none_on_404(api: respx.MockRouter, pk: PosoKanei) -> None:
    api.get("/products/barcode/404").respond(404, json={"detail": "Not found"})
    assert pk.by_barcode("404") is None


def test_price_drops(api: respx.MockRouter, pk: PosoKanei) -> None:
    api.get("/products/price-drop").respond(json=load_fixture("products_price_drop.json"))
    assert len(pk.price_drops()) == 40


def test_competitors(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get(f"/products/{PRODUCT_ID}/competitors").respond(
        json=load_fixture("product_competitors.json")
    )
    result = pk.competitors(PRODUCT_ID, retailer="sklavenitis")
    assert dict(route.calls.last.request.url.params) == {
        "retailer": "sklavenitis",
        "include_tax": "true",
    }
    assert result.id == PRODUCT_ID


# Errors


def test_404_is_not_found(api: respx.MockRouter, pk: PosoKanei) -> None:
    api.get("/products/nope").respond(404, json={"detail": "Not found"})
    with pytest.raises(NotFoundError) as caught:
        pk.product("nope")
    assert caught.value.status_code == 404
    assert "Not found" in caught.value.body


def test_403_says_what_to_check(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/meta/stats").respond(403, text="403 Forbidden")
    with pytest.raises(ForbiddenError, match="User-Agent"):
        pk.stats()
    assert route.call_count == 1  # never tried again


def test_other_4xx_is_an_api_error_and_is_not_retried(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get(f"/products/{PRODUCT_ID}/competitors").respond(
        400, json={"detail": "The 'retailer' parameter is required."}
    )
    with pytest.raises(APIError) as caught:
        pk.competitors(PRODUCT_ID, retailer="")
    assert caught.value.status_code == 400
    assert "required" in caught.value.body
    assert route.call_count == 1


def test_a_body_that_is_not_json(api: respx.MockRouter, pk: PosoKanei) -> None:
    api.get("/meta/stats").respond(200, text="<html>maintenance</html>")
    with pytest.raises(APIError, match="not JSON"):
        pk.stats()


def test_a_payload_that_does_not_fit_is_a_schema_error(
    api: respx.MockRouter, pk: PosoKanei
) -> None:
    api.get("/meta/stats").respond(json={"total_products": "many"})
    with pytest.raises(SchemaError) as caught:
        pk.stats()
    assert caught.value.payload == {"total_products": "many"}
    assert caught.value.model == "Stats"
    api.get("/products/price-drop").respond(json={"not": "a list"})
    with pytest.raises(SchemaError):
        pk.price_drops()


# Retries


def test_429_then_success(api: respx.MockRouter, pk: PosoKanei, waits: list[float]) -> None:
    route = api.get("/meta/stats").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json=load_fixture("meta_stats.json")),
        ]
    )
    assert pk.stats().retailer_count == 23
    assert route.call_count == 3
    assert len(waits) == 2
    assert 0.25 <= waits[0] <= 0.5  # half a second, less up to half of it
    assert 0.5 <= waits[1] <= 1.0  # doubled


def test_retry_after_is_honoured(api: respx.MockRouter, pk: PosoKanei, waits: list[float]) -> None:
    api.get("/meta/stats").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
            httpx.Response(429, headers={"Retry-After": "soon"}),
            httpx.Response(200, json=load_fixture("meta_stats.json")),
        ]
    )
    pk.stats()
    assert waits[0] == 7.0
    assert waits[1] == 0.0  # a date in the past
    assert 1.0 <= waits[2] <= 2.0  # unreadable: the backoff of the third try


def test_a_long_retry_after_is_not_slept_on(
    api: respx.MockRouter, pk: PosoKanei, waits: list[float]
) -> None:
    route = api.get("/products/barcode/1").respond(
        429, headers={"Retry-After": "803"}, json={"detail": "Too many barcode search requests."}
    )
    with pytest.raises(RateLimitError, match="retry after 803s") as caught:
        pk.by_barcode("1")
    assert caught.value.retry_after == 803.0
    assert route.call_count == 1
    assert waits == []


def test_429_every_time_is_a_rate_limit_error(
    api: respx.MockRouter, pk: PosoKanei, waits: list[float]
) -> None:
    route = api.get("/meta/stats").respond(429)
    with pytest.raises(RateLimitError):
        pk.stats()
    assert route.call_count == 4  # the first try and max_retries=3 more
    assert len(waits) == 3


def test_5xx_every_time_is_an_api_error(api: respx.MockRouter, waits: list[float]) -> None:
    route = api.get("/meta/stats").respond(500, text="boom")
    with PosoKanei(min_interval=0, max_retries=1) as client:
        client._sleep = waits.append
        with pytest.raises(APIError) as caught:
            client.stats()
    assert caught.value.status_code == 500
    assert not isinstance(caught.value, RateLimitError)
    assert route.call_count == 2


# Cache and rate limit


def test_a_cache_hit_makes_no_request(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    first = pk.stats()
    second = pk.stats()
    assert route.call_count == 1
    assert first == second
    assert first is not second  # parsed afresh, so changing one does not change the other


def test_the_cache_tells_requests_apart(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/products").respond(json=load_fixture("products_list.json"))
    pk.products("abc")
    pk.products("abc", page=2)
    pk.products("abc")
    assert route.call_count == 2
    search = api.post("/products/search").respond(json=load_fixture("products_search.json"))
    pk.search("γάλα")
    pk.search("ψωμί")
    pk.search("γάλα")
    assert search.call_count == 2


def test_cache_ttl_zero_turns_it_off(api: respx.MockRouter) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    with PosoKanei(min_interval=0, cache_ttl=0) as client:
        client.stats()
        client.stats()
    assert route.call_count == 2


def test_an_error_is_not_cached(api: respx.MockRouter, pk: PosoKanei) -> None:
    route = api.get("/products/barcode/1").mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200, json=load_fixture("product_by_barcode.json")),
        ]
    )
    assert pk.by_barcode("1") is None
    assert pk.by_barcode("1") is not None
    assert route.call_count == 2


def test_requests_are_spaced_and_cache_hits_do_not_wait(api: respx.MockRouter) -> None:
    api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    api.get("/products/price-drop").respond(json=[])
    now = [100.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    with PosoKanei(min_interval=0.25) as client:
        client._limiter = RateLimiter(0.25, clock=lambda: now[0], sleep=sleep)
        client.stats()  # the first request goes at once
        client.stats()  # from the cache: no wait
        assert slept == []
        now[0] += 0.1
        client.price_drops()  # 0.1s after the last request: waits out the rest
        assert slept == [pytest.approx(0.15)]
        now[0] += 1.0
        client._cache.clear()
        client.stats()  # long enough since: no wait
        assert len(slept) == 1


# The HTTP client


def test_a_transport_can_be_passed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load_fixture("meta_stats.json"))

    with PosoKanei(transport=httpx.MockTransport(handler), min_interval=0) as client:
        assert client.stats().total_products == 10150


def test_an_http_client_of_your_own_is_not_closed(api: respx.MockRouter) -> None:
    route = api.get("/meta/stats").respond(json=load_fixture("meta_stats.json"))
    with httpx.Client() as http:
        with PosoKanei(http_client=http, min_interval=0) as client:
            client.stats()
        assert not http.is_closed
    assert route.calls.last.request.headers["X-Platform"] == "flutter-web"


def test_the_default_client_checks_certificates() -> None:
    import ssl

    from posokanei._request import ssl_context

    context = ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
