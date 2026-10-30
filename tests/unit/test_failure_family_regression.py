import json
from pathlib import Path

import pytest

from benchmarks.failure_family_regression import classify_case
from healing.detector.failure_detector import FailureDetector

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "benchmarks" / "data" / "failure_family_regression_v1.json"
FIXTURE = json.loads(DATA_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["case_id"])
def test_failure_family_regression_case(case):
    result = classify_case(FailureDetector(), case)
    assert result["failure_type"] == case["expected"]


def test_detector_does_not_use_injected_ground_truth_from_context():
    detector = FailureDetector()
    exception = ValueError("Remote request timed out after 30 seconds")
    context = {
        "runtime": {"current_stage": "data_loading"},
        "failure_injection": {"requested_type": "schema_change", "ground_truth": {"failure_type": "schema_change"}},
    }
    assert detector.detect(exception, context)["failure_type"] == "unknown_runtime_failure"


def test_generic_key_error_is_not_automatically_schema_failure():
    result = FailureDetector().detect(KeyError("artifact_id"), {"runtime": {"current_stage": "artifact_verification"}})
    assert result["failure_type"] == "unknown_runtime_failure"


def test_feature_key_error_in_validation_stage_is_schema_failure():
    result = FailureDetector().detect(KeyError("feature_17"), {"runtime": {"current_stage": "feature_validation"}})
    assert result["failure_type"] == "schema_change"
