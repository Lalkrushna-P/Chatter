"""Simple in-memory sliding-window rate limiter (PRD section 40).

For production behind multiple serverless instances, replace with a shared store
(e.g. Supabase table or Redis). Values are configurable via settings.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit_per_hour: int) -> None:
        now = time.time()
        window_start = now - 3600
        dq = self._hits[key]
        while dq and dq[0] < window_start:
            dq.popleft()
        if len(dq) >= limit_per_hour:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )
        dq.append(now)


_limiter = RateLimiter()


def enforce_rate_limit(request: Request, authenticated: bool = False) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    limit = (
        settings.rate_limit_authenticated_per_hour
        if authenticated
        else settings.rate_limit_anonymous_per_hour
    )
    _limiter.check(client_ip, limit)
