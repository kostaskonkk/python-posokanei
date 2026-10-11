"""What a request is and what its answer means, with no I/O: the sync and the async client both
send the `Call`s built here, so the two cannot drift apart."""

from __future__ import annotations

import email.utils
import json
import ssl
import time
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from .errors import APIError, ForbiddenError, NotFoundError, RateLimitError, SchemaError
from .models import (
    CategoryTree,
    Competitors,
    PriceDrop,
    Product,
    ProductPage,
    Retailer,
    RetailerList,
    Stats,
)

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)
Order = Literal["asc", "desc"]

DEFAULT_BASE_URL = "https://api.posokanei.gov.gr"
# The API answers 403 to a User-Agent that is not a browser's.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:143.0) Gecko/20100101 Firefox/143.0"
)
BACKOFF_BASE = 0.5  # seconds before the first retry; doubles with each one
MAX_WAIT = 30.0  # the longest wait before a retry, ours or the server's


def default_headers(user_agent: str) -> dict[str, str]:
    """The headers of the platform's own web app."""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://posokanei.gov.gr",
        "Referer": "https://posokanei.gov.gr/",
        "X-Platform": "flutter-web",
        "X-App-Version": "1.0.0",
        "User-Agent": user_agent,
    }


def ssl_context() -> ssl.SSLContext:
    """Python's default context, certificate checks included, with OpenSSL's own cipher list.

    The API's front end answers 403 to the TLS handshake Python sends by default, whatever the
    headers (measured 2026-10-11). The same request is served with OpenSSL's stock cipher list,
    which is what curl sends.
    """
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT")
    return context


@dataclass(frozen=True)
class Call(Generic[T]):
    """One request, and how its JSON answer becomes what the method returns."""

    method: str
    path: str
    parse: Callable[[Any], T]
    params: tuple[tuple[str, str], ...] = ()
    body: Mapping[str, Any] | None = None

    def cache_key(self, base_url: str) -> Hashable:
        body = None if self.body is None else json.dumps(self.body, sort_keys=True)
        return (self.method, base_url + self.path, self.params, body)


def _query(**values: str | int | bool | None) -> tuple[tuple[str, str], ...]:
    """Query parameters as the API reads them: no None, and a bool as `true` or `false`."""
    return tuple(
        (name, str(value).lower() if isinstance(value, bool) else str(value))
        for name, value in values.items()
        if value is not None
    )


def _as(model: type[M]) -> Callable[[Any], M]:
    def parse(payload: Any) -> M:
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise SchemaError(model.__name__, payload, error) from error

    return parse


_PRICE_DROPS: TypeAdapter[list[PriceDrop]] = TypeAdapter(list[PriceDrop])


def _price_drops(payload: Any) -> list[PriceDrop]:
    try:
        return _PRICE_DROPS.validate_python(payload)
    except ValidationError as error:
        raise SchemaError("list[PriceDrop]", payload, error) from error


# One function per endpoint. `country` is the API's `countries`: "all" or an ISO code.


def retailers(*, country: str) -> Call[list[Retailer]]:
    def parse(payload: Any) -> list[Retailer]:
        # The API sends every country's retailers whatever `countries` says, so the choice is
        # made here.
        found = _as(RetailerList)(payload).retailers
        return [r for r in found if country == "all" or r.country == country]

    return Call("GET", "/meta/retailers", parse, _query(countries=country))


def categories(*, include_counts: bool, include_hidden: bool) -> Call[CategoryTree]:
    return Call(
        "GET",
        "/meta/categories/tree",
        _as(CategoryTree),
        _query(include_counts=include_counts, include_hidden=include_hidden),
    )


def products(
    category: str,
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: Order,
    country: str,
    is_international: bool | None,
) -> Call[ProductPage]:
    return Call(
        "GET",
        "/products",
        _as(ProductPage),
        _query(
            category=category,
            countries=country,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            is_international=is_international,
        ),
    )


def product(
    product_id: str,
    *,
    country: str,
    include_tax: bool,
    history: bool,
    sort_retailers: Order,
    price_type: str,
) -> Call[Product]:
    return Call(
        "GET",
        f"/products/{product_id}",
        _as(Product),
        _query(
            countries=country,
            include_tax=include_tax,
            sort_retailers=sort_retailers,
            include_history=history,
            price_type=price_type,
        ),
    )


def search(
    title: str,
    *,
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_order: Order | None,
    ids: list[str] | None,
) -> Call[ProductPage]:
    body: dict[str, Any] = {"title": title, "page": page, "page_size": page_size}
    if sort_by is not None:
        body["sort_by"] = sort_by
    if sort_order is not None:
        body["sort_order"] = sort_order
    if ids is not None:
        body["ids"] = ids
    return Call("POST", "/products/search", _as(ProductPage), body=body)


def by_barcode(ean: str, *, country: str, include_tax: bool) -> Call[Product]:
    return Call(
        "GET",
        f"/products/barcode/{ean}",
        _as(Product),
        _query(countries=country, include_tax=include_tax),
    )


def price_drops() -> Call[list[PriceDrop]]:
    return Call("GET", "/products/price-drop", _price_drops)


def competitors(product_id: str, *, retailer: str, include_tax: bool) -> Call[Competitors]:
    return Call(
        "GET",
        f"/products/{product_id}/competitors",
        _as(Competitors),
        _query(retailer=retailer, include_tax=include_tax),
    )


def stats() -> Call[Stats]:
    return Call("GET", "/meta/stats", _as(Stats))


# What an answer means.


def should_retry(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def retry_after(response: httpx.Response) -> float | None:
    """The seconds the server asks us to wait, from Retry-After: a number or a date."""
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(header)
        except ValueError:
            return None
        return max(0.0, when.timestamp() - time.time())


def retry_delay(response: httpx.Response, attempt: int, jitter: float) -> float | None:
    """Seconds to wait before retry number `attempt` (from 0), or None when the server asks for
    more than MAX_WAIT: then the answer is given up as it is, not slept on. The server's
    Retry-After wins; otherwise the wait doubles each time and `jitter` (0 to 1) takes up to
    half of it off."""
    asked = retry_after(response)
    if asked is not None:
        return asked if asked <= MAX_WAIT else None
    return min(MAX_WAIT, BACKOFF_BASE * 2.0**attempt) * (1.0 - 0.5 * jitter)


def payload(response: httpx.Response) -> Any:
    """The decoded JSON of a good answer; the error that fits a bad one."""
    status = response.status_code
    if status >= 400:
        text = response.text
        if status == 403:
            raise ForbiddenError(status, text)
        if status == 404:
            raise NotFoundError(status, text)
        if status == 429:
            raise RateLimitError(status, text, retry_after(response))
        raise APIError(status, text)
    try:
        return response.json()
    except ValueError as error:
        raise APIError(status, response.text, f"HTTP {status}: the body is not JSON") from error
