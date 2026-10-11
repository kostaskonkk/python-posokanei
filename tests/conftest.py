from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from posokanei import PosoKanei
from posokanei._request import ssl_context
from tests.contract import FIXTURE_SCHEMAS, FIXTURES, violations


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--record",
        action="store_true",
        help="with -m live: write what the API answered to tests/fixtures/",
    )


class Live:
    """A client on the real API that remembers the last payload as the API sent it, so a test can
    hold it against the spec and, with --record, keep it as a fixture."""

    def __init__(self, record: bool) -> None:
        self.record = record
        self.last: Any = None
        self._http = httpx.Client(
            timeout=30.0, verify=ssl_context(), event_hooks={"response": [self._remember]}
        )
        self.pk = PosoKanei(http_client=self._http, min_interval=1.0)

    def _remember(self, response: httpx.Response) -> None:
        response.read()
        try:
            self.last = response.json()
        except ValueError:
            self.last = None

    def check(self, fixture: str, trim: Callable[[Any], Any] = lambda payload: payload) -> None:
        """The last payload must fit the fixture's schema with no unknown field."""
        found = violations(self.last, FIXTURE_SCHEMAS[fixture])
        if self.record and not found:
            text = json.dumps(trim(self.last), ensure_ascii=False, indent=2)
            (FIXTURES / fixture).write_text(text + "\n", encoding="utf-8")
        assert found == [], f"the API no longer fits the spec ({fixture}):\n" + "\n".join(found)

    def close(self) -> None:
        self._http.close()


@pytest.fixture(scope="session")
def live(request: pytest.FixtureRequest) -> Iterator[Live]:
    session = Live(record=bool(request.config.getoption("--record")))
    yield session
    session.close()
