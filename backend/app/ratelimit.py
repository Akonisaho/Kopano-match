"""Login throttle: 5 failed attempts per account in 15 minutes, then a 15-minute lockout.

Keyed by the submitted email whether or not the account exists, so the response never reveals
which emails are registered. In-process memory only: with several server processes each keeps its
own count, and production needs a shared store such as Redis. Stated as a limit in the docs.
"""

import time
from collections import defaultdict, deque

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
_SWEEP_AT = 5000

_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(key: str, now: float) -> deque[float]:
    q = _failures[key]
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    return q


def retry_after(key: str) -> int:
    """Seconds until another attempt is allowed. 0 means allowed."""
    now = time.monotonic()
    q = _prune(key, now)
    if len(q) < MAX_FAILURES:
        return 0
    return max(1, int(WINDOW_SECONDS - (now - q[0])))


def record_failure(key: str) -> None:
    now = time.monotonic()
    if len(_failures) > _SWEEP_AT:  # bound memory against floods of made-up emails
        for k in [k for k in _failures if not _prune(k, now)]:
            del _failures[k]
    _prune(key, now).append(now)


def clear(key: str) -> None:
    _failures.pop(key, None)
