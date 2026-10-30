from benchmarks.repeated_trials import summarize


def _row(method, status, *, generation=None, duration=None, review=False):
    result = {"status": status}
    if duration is not None:
        result["method_duration_seconds"] = duration
    if review:
        result["validation_status"] = "needs_human_approval"
    row = {
        "case_id": f"case_{status}",
        "repeat_index": 0,
        "failure_type": "dependency_error" if review else "schema_change",
        "method": method,
        "result": result,
    }
    if generation is not None:
        row["llm_generation_seconds"] = generation
    if status == "recovered":
        row["candidate_id"] = "candidate-valid"
    return row


def test_summary_separates_end_to_end_recovery_from_operational_failures():
    method = "llm_direct_isolated"
    rows = [
        _row(method, "recovered", generation=10.0, duration=0.2),
        _row(method, "needs_human_approval", generation=11.0, duration=0.1, review=True),
        _row(method, "provider_quota_exhausted", generation=12.0),
        _row(method, "candidate_generation_failed", generation=13.0),
    ]

    summary = summarize(rows)
    metrics = summary["methods"][method]

    assert summary["trial_records"] == 4
    assert metrics["recovered"] == 1
    assert metrics["overall_recovery_rate"] == 0.25
    assert metrics["end_to_end_recovery_rate"] == 0.25
    assert metrics["human_review_required"] == 1
    assert metrics["automatically_eligible_cases"] == 1
    assert metrics["automatic_recovery_rate"] == 1.0
    assert metrics["provider_rate_limit_failures"] == 1
    assert metrics["operational_failure_cases"] == 2
    assert metrics["mean_llm_generation_seconds"] == 11.5
    assert metrics["generation_timed_cases"] == 4
    assert metrics["generation_plus_method_timed_cases"] == 2
    assert metrics["valid_candidate_generation_timed_cases"] == 1


def test_summary_keeps_rule_based_clean_denominator_unchanged():
    method = "rule_based_gated"
    rows = [
        _row(method, "recovered", duration=0.2),
        _row(method, "recovered", duration=0.3),
        _row(method, "needs_human_approval", duration=0.01, review=True),
    ]

    metrics = summarize(rows)["methods"][method]
    assert metrics["cases"] == 3
    assert metrics["recovered"] == 2
    assert metrics["overall_recovery_rate"] == 2 / 3
    assert metrics["automatically_eligible_cases"] == 2
    assert metrics["automatic_recovery_rate"] == 1.0
    assert metrics["human_review_required"] == 1


def test_capture_audit_reports_status_and_rate_limit_counts_without_payloads(tmp_path):
    import json
    from benchmarks.repeated_trials import _audit_capture_log

    path = tmp_path / "capture.jsonl"
    records = [
        {
            "timestamp_utc": "2026-10-27T10:00:00+00:00",
            "status": "response_received",
            "request": {"messages": [{"content": "SENSITIVE_PROMPT_SHOULD_NOT_BE_IN_SUMMARY"}]},
            "response": {"content": "SENSITIVE_RESPONSE_SHOULD_NOT_BE_IN_SUMMARY"},
        },
        {
            "timestamp_utc": "2026-10-27T10:01:00+00:00",
            "status": "request_failed",
            "error": {"type": "RateLimitError", "message_redacted": "HTTP 429 rate limit"},
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\nnot-json\n")

    audit = _audit_capture_log(path)

    assert audit["records"] == 2
    assert audit["malformed_jsonl_lines"] == 1
    assert audit["status_counts"] == {"request_failed": 1, "response_received": 1}
    assert audit["rate_limit_failed_interactions"] == 1
    assert audit["first_interaction_utc"].startswith("2026-10-27T10:00:00")
    assert "SENSITIVE_PROMPT" not in json.dumps(audit)
    assert "SENSITIVE_RESPONSE" not in json.dumps(audit)
