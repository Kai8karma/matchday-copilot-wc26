"""Input hygiene, rate limiting, and response security headers."""

from __future__ import annotations

import html
import re
import threading
import time

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Match real markup (<tag ...>, </tag>, <!-- -->) but not prose like "a < b".
_TAGS = re.compile(r"</?[a-zA-Z!][^>]{0,200}>")


def sanitize(text: str, limit: int = 500) -> str:
    """Neutralize markup/control chars and cap length.

    Tags are stripped and remaining angle brackets entity-escaped. Quotes are
    deliberately preserved (quote=False) so multilingual contractions like
    "j'ai" survive intent tokenization; the frontend renders exclusively via
    textContent, never innerHTML or attributes, so preserved quotes cannot
    reach an executable context.
    """
    text = _CONTROL.sub("", text)
    text = _TAGS.sub(" ", text)
    text = html.escape(text, quote=False)
    return " ".join(text.split())[:limit]


class RateLimiter:
    """Fixed-window per-client limiter (in-memory; one process = one window).

    Suitable for a demo/single instance; swap for Redis in multi-instance
    deployments.
    """

    def __init__(self, limit: int = 30, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            start, count = self._hits.get(client_id, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[client_id] = (start, count)
            if len(self._hits) > 10_000:  # bound memory under address churn
                self._hits = {
                    k: v for k, v in self._hits.items() if now - v[0] < self.window
                }
            return count <= self.limit


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'"
    ),
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}
