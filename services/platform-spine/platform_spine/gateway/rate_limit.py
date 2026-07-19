import time
from collections import defaultdict
from fastapi import HTTPException

WINDOW_SECONDS = 60
DEFAULT_MAX_REQUESTS = 60

_request_log: dict[str, list] = defaultdict(list)


def check_rate_limit(actor: str, max_requests: int = DEFAULT_MAX_REQUESTS):
    now = time.time()
    log = _request_log[actor]
    while log and log[0] < now - WINDOW_SECONDS:
        log.pop(0)
    if len(log) >= max_requests:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    log.append(now)


def reset():
    """Test-only: clears all rate-limit state between test runs."""
    _request_log.clear()
