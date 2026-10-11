"""The asynchronous client: PosoKanei with `await`."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Any

import httpx

from . import _request
from ._cache import TTLCache
from ._ratelimit import AsyncRateLimiter
from ._request import Call, Order, T
from .errors import NotFoundError
from .models import (
    CategoryTree,
    Competitors,
    PriceDrop,
    Product,
    ProductPage,
    Retailer,
    Stats,
)

logger = logging.getLogger("posokanei")


class AsyncPosoKanei:
    """A client for the price API behind posokanei.gov.gr.

    Requests are at least `min_interval` seconds apart, an answer is kept for `cache_ttl` seconds
    (0 turns the cache off), and a 429 or a 5xx is tried again up to `max_retries` times, unless
    the API asks for a wait of more than half a minute: that is raised at once.

    Pass `http_client` to use an `httpx.AsyncClient` of your own: it is then yours to configure and
    to close, and `timeout` and `transport` are not applied to it.
    """

    def __init__(
        self,
        *,
        base_url: str = _request.DEFAULT_BASE_URL,
        user_agent: str = _request.DEFAULT_USER_AGENT,
        timeout: float = 15.0,
        min_interval: float = 0.25,
        cache_ttl: float = 300.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = _request.default_headers(user_agent)
        self._max_retries = max_retries
        self._owns_http = http_client is None
        if http_client is not None:
            self._http = http_client
        elif transport is not None:
            self._http = httpx.AsyncClient(timeout=timeout, transport=transport)
        else:
            self._http = httpx.AsyncClient(timeout=timeout, verify=_request.ssl_context())
        self._limiter = AsyncRateLimiter(min_interval)
        self._cache = TTLCache(cache_ttl)
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncPosoKanei:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    # The endpoints

    async def retailers(self, *, country: str = "GR") -> list[Retailer]:
        """The retailers of a country, or of every country with `country="all"`."""
        return await self._send(_request.retailers(country=country))

    async def categories(
        self, *, include_counts: bool = True, include_hidden: bool = False
    ) -> CategoryTree:
        """The category tree. A node's `category_id` is what `products` takes."""
        return await self._send(
            _request.categories(include_counts=include_counts, include_hidden=include_hidden)
        )

    async def products(
        self,
        category: str,
        *,
        page: int = 1,
        page_size: int = 36,
        sort_by: str = "unit_price",
        sort_order: Order = "asc",
        country: str = "GR",
        is_international: bool | None = None,
    ) -> ProductPage:
        """One page of a category's products."""
        return await self._send(
            _request.products(
                category,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                country=country,
                is_international=is_international,
            )
        )

    async def aiter_products(
        self,
        category: str,
        *,
        page_size: int = 36,
        sort_by: str = "unit_price",
        sort_order: Order = "asc",
        country: str = "GR",
        is_international: bool | None = None,
    ) -> AsyncIterator[Product]:
        """Every product of a category, page after page until the API says there is no next."""
        page = 1
        while True:
            result = await self.products(
                category,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                country=country,
                is_international=is_international,
            )
            for item in result.products:
                yield item
            if not result.has_next or not result.products:
                return
            page += 1

    async def product(
        self,
        product_id: str,
        *,
        country: str = "all",
        include_tax: bool = True,
        history: bool = False,
        sort_retailers: Order = "asc",
        price_type: str = "unit_price",
    ) -> Product:
        """One product with its price at every retailer; `history=True` adds the daily prices."""
        return await self._send(
            _request.product(
                product_id,
                country=country,
                include_tax=include_tax,
                history=history,
                sort_retailers=sort_retailers,
                price_type=price_type,
            )
        )

    async def search(
        self,
        title: str,
        *,
        page: int = 1,
        page_size: int = 36,
        sort_by: str | None = None,
        sort_order: Order | None = None,
        ids: list[str] | None = None,
    ) -> ProductPage:
        """Products whose title matches."""
        return await self._send(
            _request.search(
                title,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                ids=ids,
            )
        )

    async def by_barcode(
        self, ean: str, *, country: str = "GR", include_tax: bool = True
    ) -> Product | None:
        """The product with this barcode, or None if the API answers 404."""
        try:
            return await self._send(
                _request.by_barcode(ean, country=country, include_tax=include_tax)
            )
        except NotFoundError:
            return None

    async def price_drops(self) -> list[PriceDrop]:
        """Every active price drop. The API does not page this list."""
        return await self._send(_request.price_drops())

    async def competitors(
        self, product_id: str, *, retailer: str, include_tax: bool = True
    ) -> Competitors:
        """The products of the same category, each with its price at `retailer` (a retailer id)."""
        return await self._send(
            _request.competitors(product_id, retailer=retailer, include_tax=include_tax)
        )

    async def stats(self) -> Stats:
        """The platform's statistics: how many products, which retailers."""
        return await self._send(_request.stats())

    # Sending

    async def _send(self, call: Call[T]) -> T:
        key = call.cache_key(self._base_url)
        hit, payload = self._cache.get(key)
        if not hit:
            payload = await self._fetch(call)
            self._cache.set(key, payload)
        return call.parse(payload)

    async def _fetch(self, call: Call[Any]) -> Any:
        url = self._base_url + call.path
        attempt = 0
        while True:
            await self._limiter.wait()
            response = await self._http.request(
                call.method, url, params=call.params, json=call.body, headers=self._headers
            )
            logger.debug("%s %s %s -> %d", call.method, url, call.params, response.status_code)
            if _request.should_retry(response.status_code) and attempt < self._max_retries:
                delay = _request.retry_delay(response, attempt, random.random())
                if delay is not None:
                    logger.debug("retry %d in %.2fs", attempt + 1, delay)
                    await self._sleep(delay)
                    attempt += 1
                    continue
            return _request.payload(response)
