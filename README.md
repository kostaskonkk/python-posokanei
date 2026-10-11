# posokanei

**Unofficial** Python client for the price API behind [posokanei.gov.gr](https://posokanei.gov.gr),
the Greek government's supermarket price observatory. It is not affiliated with posokanei.gov.gr
or with the Greek Ministry of Development.

The platform publishes no API documentation. This package gives you typed
[Pydantic](https://docs.pydantic.dev) models, a sync and an async client, and a hand-written
[OpenAPI 3.1 description of the API](spec/openapi.yaml) that you can use from any language.

```
pip install posokanei
```

Python 3.10 or newer.

## The official site

[posokanei.gov.gr](https://posokanei.gov.gr) is the platform's own interface, and the place to go
if you just want to look up a price: browse the categories, search a product, compare its price
across supermarkets and countries, see its price history and the current price drops. This
package reads the same API that site does, so what you get here is what you see there.

## Quickstart

```python
from posokanei import PosoKanei

with PosoKanei() as pk:
    greek = pk.retailers(country="GR")
    print([retailer.id for retailer in greek])  # 'sklavenitis', 'ab_vasilopoulos', 'lidl', ...

    tree = pk.categories()
    category = tree.tree[0].children[0].children[0]  # a category's id is what products() takes

    page = pk.products(category.category_id, sort_by="unit_price", sort_order="asc")
    cheapest = page.products[0]
    print(cheapest.name, cheapest.price_stats.min_unit_price, "EUR per", cheapest.unit)

    product = pk.product(cheapest.id, history=True)
    for price in product.retailer_prices:
        print(price.retailer, price.price)
    for retailer, days in product.history.daily_prices.items():
        print(retailer, days[0].date, days[0].price, "->", days[-1].date, days[-1].price)
```

## What it covers

| Method | Returns | Request |
|---|---|---|
| `retailers(country="GR")` | `list[Retailer]` | `GET /meta/retailers` |
| `categories(include_counts=True, include_hidden=False)` | `CategoryTree` | `GET /meta/categories/tree` |
| `products(category, page=1, page_size=36, ...)` | `ProductPage` | `GET /products` |
| `iter_products(category, ...)` | every `Product`, page after page | `GET /products` |
| `product(id, history=False, ...)` | `Product` | `GET /products/{id}` |
| `search(title, page=1, page_size=36, ...)` | `ProductPage` | `POST /products/search` |
| `by_barcode(ean)` | `Product` or `None` | `GET /products/barcode/{ean}` |
| `price_drops()` | `list[PriceDrop]` | `GET /products/price-drop` |
| `competitors(id, retailer=...)` | `Competitors` | `GET /products/{id}/competitors` |
| `stats()` | `Stats` | `GET /meta/stats` |

`AsyncPosoKanei` has the same methods with `await`, and `aiter_products` for `iter_products`:

```python
async with AsyncPosoKanei() as pk:
    page = await pk.search("γάλα")
```

`country` is `"all"` or an ISO country code. A price is in EUR; `price_normalized` and the unit
prices are EUR per `unit` of the product (`kg`, `L`, ...). Timestamps have no offset and are UTC.

Things the API does that you might not expect:

- `price_drops()` is not paged: one call returns every active price drop, about 1,800 items.
- `/meta/retailers` returns every country's retailers whatever you ask for, so `retailers()`
  picks the country's on your side.
- `competitors()` needs a retailer id, and gives the other products of the same category with
  their price at that retailer.
- A product no retailer has a price for has `price_stats = None` and empty lists.
- The barcode endpoint has a much tighter rate limit than the rest: after a handful of requests
  it answers 429 and asks for a wait of about a quarter of an hour.

Search, barcode, competitors and stats each rest on a single recorded response, so their models
are the least certain. That a barcode nobody knows gives a 404, and so `None`, is reported by
posokanei-mcp and has not been seen here.

## Errors

Everything the package raises itself derives from `PosoKaneiError`:

| Error | When |
|---|---|
| `NotFoundError` | 404 |
| `ForbiddenError` | 403, see below |
| `RateLimitError` | 429, still, after the retries |
| `APIError` | any other 4xx or 5xx, or a body that is not JSON. Has `status_code` and `body` |
| `SchemaError` | the answer does not fit its model. Has `payload`, what the API sent |

A network failure stays an `httpx` exception.

The models accept fields they do not know (they end up in `model_extra`), so a field added
upstream does not break your code. A field that goes missing or changes type raises `SchemaError`.

## Be polite

This is a public service, so the defaults are careful, and please keep them that way:

- at least 0.25 seconds between two requests (`min_interval`),
- an answer is kept in memory for five minutes (`cache_ttl`; 0 turns it off),
- a 429 or a 5xx is tried again up to three times with a growing wait, and a `Retry-After` is
  honoured. When the API asks for more than half a minute, the client does not sit it out: it
  raises `RateLimitError` at once, with the wait in `retry_after`.

The prices belong to the platform. If you want history in bulk, use the dataset at
[spyrosavl/posokanei](https://github.com/spyrosavl/posokanei) instead of crawling the API.

## If you get a 403

The API refuses requests that do not look like its web app's. Measured on 2026-10-11:

- The `User-Agent` has to be a browser's. The client sends one by default (`user_agent=`), along
  with the web app's `Origin`, `Referer`, `X-Platform` and `X-App-Version`.
- It also refuses some clients whatever their headers. Python's default TLS settings were
  refused; the same request with OpenSSL's default cipher list was served. The client therefore
  builds its connection that way (certificates are checked as usual). If you pass an
  `http_client` of your own, give it `verify=posokanei._request.ssl_context()`.

None of this is documented by the platform and it can change without notice.

## The API description

[`spec/openapi.yaml`](spec/openapi.yaml) is the source of truth of this package: the models in
`src/posokanei/models.py` are generated from it. It stands on its own as documentation of the
API, written from the recorded responses in [`tests/fixtures/`](tests/fixtures).

## Development

```
uv sync
uv run make check    # ruff, mypy --strict, the tests
uv run make models   # after a change to spec/openapi.yaml; never edit models.py by hand
uv run make live     # calls the real API, about ten requests
```

`make live` holds every answer against the spec with unknown fields forbidden. That is how a
change upstream is noticed: run it when something looks off, or on a schedule.
`make live ARGS=--record` also writes the answers to `tests/fixtures/`.

How to change the spec, add an endpoint or report that the API changed is in
[CONTRIBUTING.md](CONTRIBUTING.md); what changed between versions is in [CHANGELOG.md](CHANGELOG.md).

## Credits

The search, barcode, stats and competitors endpoints were found by
[charistas/posokanei-mcp](https://github.com/charistas/posokanei-mcp) (MIT).

## License

MIT
