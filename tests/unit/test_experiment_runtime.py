from types import SimpleNamespace

import pytest

from benchmarks.experiment_runtime import (
    ProviderQuotaExhausted,
    ProviderRateLimitDeferred,
    _parse_duration_seconds,
    is_daily_quota_error,
    run_with_rate_limit_retry,
)


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self, message, headers=None):
        super().__init__(message)
        self.response = SimpleNamespace(headers=headers or {}, status_code=429)


def quiet_reporter(message, level):
    return None


def test_daily_token_limit_stops_without_retry_or_sleep():
    calls = []
    waits = []

    def call():
        calls.append(1)
        raise FakeRateLimitError(
            "Rate limit reached: limit 200000, tokens per day (TPD) exhausted"
        )

    with pytest.raises(ProviderQuotaExhausted):
        run_with_rate_limit_retry(
            call,
            max_attempts=5,
            sleeper=waits.append,
            reporter=quiet_reporter,
        )

    assert len(calls) == 1
    assert waits == []


def test_temporary_rate_limit_retries_using_retry_after():
    calls = []
    waits = []

    def call():
        calls.append(1)
        if len(calls) == 1:
            raise FakeRateLimitError(
                "Too many requests", headers={"Retry-After": "2"}
            )
        return "ok"

    value = run_with_rate_limit_retry(
        call,
        max_attempts=3,
        max_wait_seconds=30,
        sleeper=waits.append,
        reporter=quiet_reporter,
    )

    assert value == "ok"
    assert len(calls) == 2
    assert waits == [2.0]


def test_long_rate_limit_window_is_deferred_without_sleeping():
    calls = []
    waits = []

    def call():
        calls.append(1)
        raise FakeRateLimitError(
            "Too many requests",
            headers={"retry-after": "120"},
        )

    with pytest.raises(ProviderRateLimitDeferred, match="exceeds configured maximum"):
        run_with_rate_limit_retry(
            call,
            max_attempts=3,
            max_wait_seconds=30,
            sleeper=waits.append,
            reporter=quiet_reporter,
        )

    assert len(calls) == 1
    assert waits == []


def test_non_rate_limit_exception_is_not_retried():
    calls = []
    waits = []

    def call():
        calls.append(1)
        raise ValueError("bad synthetic fixture")

    with pytest.raises(ValueError, match="synthetic fixture"):
        run_with_rate_limit_retry(
            call,
            max_attempts=4,
            sleeper=waits.append,
            reporter=quiet_reporter,
        )

    assert len(calls) == 1
    assert waits == []


def test_provider_daily_quota_classifier_recognizes_tpd_and_rpd():
    assert is_daily_quota_error(
        FakeRateLimitError("Tokens per day (TPD) limit reached")
    )
    assert is_daily_quota_error(
        FakeRateLimitError("Requests per day (RPD) limit reached")
    )
    assert not is_daily_quota_error(
        FakeRateLimitError("Temporary tokens per minute limit")
    )


def test_retry_duration_parser_supports_provider_reset_formats():
    assert _parse_duration_seconds("2") == 2.0
    assert _parse_duration_seconds("7.66s") == pytest.approx(7.66)
    assert _parse_duration_seconds("4m21.792s") == pytest.approx(261.792)
    assert _parse_duration_seconds("1h2m") == pytest.approx(3720)
    assert _parse_duration_seconds("not a duration") is None
