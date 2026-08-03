"""Exponential-backoff retry for the handful of external calls in this
pipeline (YouTube API, Claude, video-gen provider, upload). Not a general
resilience framework -- just enough to survive transient network blips
without the whole run dying and needing a manual re-trigger.
"""
from __future__ import annotations

import functools
import logging
import time

logger = logging.getLogger(__name__)


def with_retry(*, attempts: int = 3, base_delay: float = 2.0, exceptions: tuple[type[Exception], ...] = (Exception,)):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"{fn.__name__} failed (attempt {attempt}/{attempts}): {exc}. Retrying in {delay:.0f}s..."
                    )
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
