# Changelog

What changed for someone who uses the package. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0 a minor version may change
the public API; a change in the upstream API that forces one is noted as such.

## [Unreleased]

### Added

- `PosoKanei` and `AsyncPosoKanei`, with `retailers`, `categories`, `products`, `iter_products`
  (`aiter_products`), `product`, `search`, `by_barcode`, `price_drops`, `competitors` and `stats`.
- Pydantic v2 models for every response, generated from the spec. They keep fields they do not
  know in `model_extra`.
- `spec/openapi.yaml`: an OpenAPI 3.1 description of the API, written from recorded responses.
- A rate limit (0.25 s between requests), an in-memory cache (five minutes) and retries on 429
  and 5xx that honour `Retry-After`. A wait of more than 30 seconds is raised as
  `RateLimitError` with `retry_after`, not slept on.
- Errors: `PosoKaneiError`, `APIError`, `NotFoundError`, `ForbiddenError`, `RateLimitError`,
  `SchemaError`.
- Live tests (`make live`) that hold the real API against the spec with unknown fields forbidden.

[Unreleased]: https://github.com/kostaskonkk/python-posokanei/commits/main
