from __future__ import annotations

from posokanei import _cache
from posokanei._cache import TTLCache


def test_an_entry_expires() -> None:
    now = [0.0]
    cache = TTLCache(10, clock=lambda: now[0])
    cache.set("a", None)
    assert cache.get("a") == (True, None)  # a kept None is still a hit
    now[0] = 9.9
    assert cache.get("a") == (True, None)
    now[0] = 10.0
    assert cache.get("a") == (False, None)
    assert cache.get("never") == (False, None)


def test_it_does_not_grow_without_end() -> None:
    now = [0.0]
    cache = TTLCache(10, clock=lambda: now[0])
    for number in range(_cache.MAX_ENTRIES):
        cache.set(number, number)
    cache.set("one more", 1)  # nothing has expired: the oldest goes
    assert cache.get(0) == (False, None)
    assert cache.get(1) == (True, 1)
    now[0] = 5.0
    cache.set("later", 2)
    now[0] = 11.0
    cache.set("fresh", 3)  # everything put in at 0 has expired and is dropped
    assert cache.get("later") == (True, 2)
    assert cache.get("fresh") == (True, 3)
    assert cache.get(1) == (False, None)
