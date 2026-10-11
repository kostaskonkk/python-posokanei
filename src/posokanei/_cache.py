"""An in-memory cache whose entries expire. One per client."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

MAX_ENTRIES = 1024


class TTLCache:
    """Keeps a value for `ttl` seconds. A `ttl` of 0 keeps nothing."""

    def __init__(self, ttl: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = ttl
        self._clock = clock
        self._entries: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> tuple[bool, Any]:
        """(True, value) on a hit, (False, None) otherwise: a cached value may itself be None."""
        if self.ttl <= 0:
            return False, None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            expires, value = entry
            if expires <= self._clock():
                del self._entries[key]
                return False, None
            return True, value

    def set(self, key: Hashable, value: Any) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            now = self._clock()
            if len(self._entries) >= MAX_ENTRIES:
                self._entries = {k: e for k, e in self._entries.items() if e[0] > now}
            while len(self._entries) >= MAX_ENTRIES:
                del self._entries[next(iter(self._entries))]  # the oldest one put in
            self._entries[key] = (now + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
