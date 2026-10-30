"""Runtime helpers for visible, quota-aware live experiments.

This module deliberately avoids importing the OpenAI SDK so offline tooling and
unit tests can inspect benchmark behavior without installing optional LLM deps.
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Any


class ProviderQuotaExhausted(RuntimeError):
    """A provider indicated that a daily/long-window quota is exhausted."""


class ProviderRateLimitDeferred(RuntimeError):
    """A temporary rate limit requires a wait longer than this run allows."""


def progress(message: str, level: str = "INFO") -> None:
    """Print an unbuffered UTC progress line suitable for terminal or tee logs."""
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"[{stamp}] [{level}] {message}", flush=True)


def _safe_text(exc: BaseException) -> str:
    """Return only the short error text needed to classify provider behavior."""
    try:
        text = str(exc)
    except Exception:
        text = type(exc).__name__
    # Redact common credential shapes before this text can reach logs/artifacts.
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{16,}\b", "<redacted-secret>", text)
    text = re.sub(r"(?i)\bgsk_[A-Za-z0-9_-]{16,}\b", "<redacted-secret>", text)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", text)
    text = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|password|passwd|secret|authorization)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2<redacted>", text,
    )
    return text[:1200]


def safe_error_summary(exc: BaseException) -> str:
    """Credential-scrubbed, length-limited text for result records."""
    return f"{type(exc).__name__}: {_safe_text(exc)}"[:1400]


def _headers(exc: BaseException) -> dict[str, str]:
    response = getattr(exc, "response", None)
    raw = getattr(response, "headers", None)
    if not raw:
        return {}
    try:
        return {str(key).lower(): str(value).strip() for key, value in raw.items()}
    except Exception:
        return {}


def is_rate_limit_error(exc: BaseException) -> bool:
    """Recognize SDK RateLimitError or compatible HTTP 429 exceptions."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return True
    name = type(exc).__name__.lower()
    text = _safe_text(exc).lower()
    return "ratelimit" in name or ("429" in text and "rate limit" in text)


def is_daily_quota_error(exc: BaseException) -> bool:
    """Detect daily/long-window exhaustion that must not be retried immediately."""
    text = _safe_text(exc).lower()
    markers = (
        "tokens per day", "token per day", "tpd", "requests per day",
        "request per day", "rpd", "daily quota", "daily limit",
        "quota for the day", "daily token limit",
    )
    if any(marker in text for marker in markers):
        return True

    # Groq exposes limit/reset headers. RPD is a daily request quota there;
    # do not infer daily exhaustion from a generic zero TPM/remaining-token value.
    headers = _headers(exc)
    remaining_requests = headers.get("x-ratelimit-remaining-requests")
    limit_requests = headers.get("x-ratelimit-limit-requests")
    reset_requests = headers.get("x-ratelimit-reset-requests", "")
    if remaining_requests == "0" and limit_requests and reset_requests:
        if _parse_duration_seconds(reset_requests) is not None:
            return True
    return False


def _parse_duration_seconds(value: str | None) -> float | None:
    """Parse retry hints such as 2, 7.6s, 4m21.7s, or 1h2m."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        number = float(raw)
        if number >= 0:
            return number
    except ValueError:
        pass

    parts = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)", raw.lower()))
    if not parts:
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None

    total = 0.0
    for part in parts:
        number = float(part.group(1))
        unit = part.group(2)
        scale = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        total += number * scale
    return total


def retry_delay_seconds(exc: BaseException) -> float | None:
    """Read Retry-After/reset headers or a provider's human-readable wait hint."""
    headers = _headers(exc)
    for key in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        delay = _parse_duration_seconds(headers.get(key))
        if delay is not None:
            return delay

    text = _safe_text(exc)
    match = re.search(
        r"(?:try again|retry|reset)(?: in)?\s+((?:\d+(?:\.\d+)?\s*(?:ms|s|m|h)\s*)+)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return _parse_duration_seconds(match.group(1))
    return None


def run_with_rate_limit_retry(
    fn: Callable[[], Any],
    *,
    max_attempts: int = 4,
    max_wait_seconds: float = 30.0,
    sleeper: Callable[[float], None] | None = None,
    reporter: Callable[[str, str], None] | None = None,
) -> Any:
    """Retry temporary HTTP 429s; stop immediately on daily quota exhaustion.

    Long reset windows are deferred rather than sleeping through the experiment.
    Non-rate-limit exceptions pass through unchanged.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if max_wait_seconds < 0:
        raise ValueError("max_wait_seconds cannot be negative")

    wait = sleeper or time.sleep
    report = reporter or progress

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_rate_limit_error(exc):
                raise

            if is_daily_quota_error(exc):
                report(
                    "Provider daily quota is exhausted (TPD/RPD). Stopping new LLM calls; "
                    "the benchmark will save a partial result.",
                    "ERROR",
                )
                raise ProviderQuotaExhausted(
                    "Provider daily token/request quota exhausted; no immediate retry attempted."
                ) from exc

            if attempt >= max_attempts:
                report(
                    f"Temporary provider rate limit persisted after {max_attempts} attempts; "
                    "stopping this run with a partial result.",
                    "ERROR",
                )
                raise ProviderRateLimitDeferred(
                    f"Temporary rate limit persisted after {max_attempts} attempts."
                ) from exc

            hinted = retry_delay_seconds(exc)
            if hinted is not None and hinted > max_wait_seconds:
                report(
                    f"Provider requests a {hinted:.1f}s wait, above the configured "
                    f"{max_wait_seconds:.1f}s maximum. Deferring remaining LLM work.",
                    "WARNING",
                )
                raise ProviderRateLimitDeferred(
                    f"Provider retry window ({hinted:.1f}s) exceeds configured maximum "
                    f"({max_wait_seconds:.1f}s)."
                ) from exc

            delay = hinted if hinted is not None else min(
                (2 ** (attempt - 1)) + random.uniform(0, 0.25),
                max_wait_seconds,
            )
            report(
                f"Temporary HTTP 429; retrying in {delay:.2f}s "
                f"(attempt {attempt + 1}/{max_attempts}).",
                "WARNING",
            )
            wait(delay)

    raise RuntimeError("Unexpected exit from rate-limit retry loop.")
