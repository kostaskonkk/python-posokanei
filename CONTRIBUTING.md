# Contributing

Thanks for helping. This is a small, unofficial client of an API nobody documents, so the most
useful contributions are the ones that say what the API really does: a field that changed, an
endpoint that is missing, a response the models refuse.

## Setting up

You need [uv](https://docs.astral.sh/uv/) and `make`.

```
uv sync
uv run make check
```

`make check` is ruff, `mypy --strict` and the tests. None of them touches the network.

## The spec comes first

`spec/openapi.yaml` is the source of truth. `src/posokanei/models.py` is generated from it and is
never edited by hand; CI fails when the two disagree.

To change what a response looks like:

1. Change `spec/openapi.yaml`.
2. `uv run make models`, and commit the regenerated `models.py` with it.
3. Add or update a fixture in `tests/fixtures/` that shows the change. A fixture is a real
   response, cut down if it is large, with nothing but the public payload: no headers, no cookies.
4. `uv run make check`. The contract test holds every fixture against the spec and fails on a
   field the spec does not name.

Do not describe a shape you have not seen. If a field has only ever been null, say so in its
description and leave it nullable.

To add an endpoint, add it to the spec the same way, then a function for it in
`src/posokanei/_request.py` and a method on both clients (`client.py` and `aclient.py`), which
only differ in `await`. Tests for both go in `tests/test_client.py` and `tests/test_aclient.py`.

## The real API

```
uv run make live                 # about ten requests, a second apart
uv run make live ARGS=--record   # and write the answers to tests/fixtures/
```

Run these by hand and sparingly. posokanei.gov.gr is a public service and it limits by address;
the barcode endpoint allows only a handful of requests in a quarter of an hour. CI never calls
the real API. After `--record`, the values some tests check (counts, ids, dates) need a look,
because the recording picks its own category and product.

Never commit a HAR file, cookies or anything personal.

## Reporting that the API changed

Open an issue with the request you made (method, path, parameters) and what came back: the
`SchemaError` message, or the output of `make live`. If you can, attach the response body.

## Pull requests

- One change per pull request, with a line in `CHANGELOG.md` under Unreleased when a user of the
  package would notice it.
- Keep the defaults polite: the rate limit, the cache and the retries are there for the service's
  sake.
- A change to the public methods or their arguments needs an issue first.

## Releasing

For maintainers: set `__version__` in `src/posokanei/__init__.py`, move the Unreleased entries
under the new version in `CHANGELOG.md`, and push a tag `v<version>`. The release workflow checks
that the tag matches, builds and publishes to PyPI through trusted publishing.

By contributing you agree that your work is released under the MIT license of this project.
