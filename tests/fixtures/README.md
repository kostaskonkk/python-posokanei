# Fixtures

Real responses of `api.posokanei.gov.gr`, recorded on 2026-10-11. Public data only: no headers,
no cookies. Some are cut down to keep the repository small; the shape of what is left is untouched.

| File | Request | Cut |
|---|---|---|
| `meta_retailers.json` | `GET /meta/retailers?countries=all` | no |
| `meta_categories_tree.json` | `GET /meta/categories/tree?include_counts=true` | the first 2 of 19 root categories |
| `products_list.json` | `GET /products?category=…&page=1&page_size=36&sort_by=unit_price&sort_order=asc` | no |
| `product_detail.json`, `product_detail_2.json` | `GET /products/{id}` | no |
| `product_history.json` | `GET /products/{id}?include_history=true` | no |
| `products_price_drop.json` | `GET /products/price-drop` | 40 of 1,792 items, two of them without dates |
| `products_search.json` | `POST /products/search`, title `γάλα`, `page_size` 5 | no |
| `product_by_barcode.json` | `GET /products/barcode/0000000000000` | no |
| `product_competitors.json` | `GET /products/{id}/competitors?retailer=sklavenitis` | 6 of 51: three with a price, three without |
| `meta_stats.json` | `GET /meta/stats` | no |

`pytest -m live --record` writes them again from the live API, except `product_detail_2.json`.
It picks its own category and product, so the values `tests/test_models.py` and
`tests/test_client.py` check (counts, ids, dates) need a look afterwards.
