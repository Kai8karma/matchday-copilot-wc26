"""Input sanitization and rate limiting."""

from app.security import RateLimiter, sanitize


def test_sanitize_strips_script_tags() -> None:
    out = sanitize("<script>alert('x')</script>hello")
    assert "<script>" not in out
    assert "hello" in out


def test_sanitize_escapes_remaining_angle_brackets() -> None:
    out = sanitize("a < b and c > d")
    assert "<" not in out
    assert "&lt;" in out


def test_sanitize_removes_control_characters() -> None:
    assert sanitize("hi\x00\x1bthere") == "hithere"


def test_sanitize_caps_length() -> None:
    assert len(sanitize("x" * 2000)) == 500


def test_rate_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    results = [limiter.allow("1.2.3.4", now=100.0 + i) for i in range(5)]
    assert results == [True, True, True, False, False]


def test_rate_limiter_resets_after_window() -> None:
    limiter = RateLimiter(limit=1, window_seconds=10)
    assert limiter.allow("ip", now=0.0)
    assert not limiter.allow("ip", now=5.0)
    assert limiter.allow("ip", now=11.0)


def test_rate_limiter_isolates_clients() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a", now=0.0)
    assert limiter.allow("b", now=0.0)
