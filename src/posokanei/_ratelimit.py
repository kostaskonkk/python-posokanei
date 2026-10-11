"""At least `min_interval` seconds between two requests of one client."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last: float | None = None

    def wait(self) -> None:
        """Returns when the next request may go, and counts it as gone."""
        with self._lock:
            if self._last is not None:
                remaining = self._last + self.min_interval - self._clock()
                if remaining > 0:
                    self._sleep(remaining)
            self._last = self._clock()


class AsyncRateLimiter:
    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last: float | None = None

    async def wait(self) -> None:
        async with self._lock:
            if self._last is not None:
                remaining = self._last + self.min_interval - self._clock()
                if remaining > 0:
                    await self._sleep(remaining)
            self._last = self._clock()
