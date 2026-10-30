import pytest

from healing.detector.failure_detector import FailureDetector
from healing.detector.schema_detector import is_schema_failure
from healing.detector.data_quality_detector import is_data_quality_failure
from healing.detector.config_detector import is_configuration_failure
from healing.detector.runtime_detector import is_dependency_failure


@pytest.mark.parametrize(
    "exception, expected_type, expected_confidence",
    [
        (
            ValueError("Schema mismatch | missing=['a'] | unexpected=['b']"),
            "schema_change",
            0.95,
        ),
        (
            ValueError("Input contains NaN values"),
            "data_quality",
            0.95,
        ),
        (
            ValueError("Invalid parameter C"),
            "configuration_error",
            0.97,
        ),
        (
            ModuleNotFoundError("No module named 'fake_package'"),
            "dependency_error",
            0.99,
        ),
        (
            ValueError("Unrecognized runtime problem"),
            "unknown_runtime_failure",
            0.40,
        ),
    ],
)
def test_failure_detector_classifies_exceptions(
    exception, expected_type, expected_confidence
):
    result = FailureDetector().detect(exception, {})

    assert result["failure_type"] == expected_type
    assert result["confidence"] == expected_confidence
    assert result["reason"]


def test_schema_detector_recognizes_schema_mismatch():
    exc = ValueError("Schema mismatch detected")

    assert is_schema_failure(exc)


def test_schema_detector_recognizes_missing_column():
    exc = KeyError("feature_x")

    assert is_schema_failure(exc)


def test_schema_detector_rejects_unrelated_error():
    exc = ValueError("Network connection failed")

    assert not is_schema_failure(exc)


def test_data_quality_detector_recognizes_nan():
    assert is_data_quality_failure(
        ValueError("Input contains NaN values")
    )


def test_data_quality_detector_recognizes_infinity():
    assert is_data_quality_failure(
        ValueError("Input contains infinity")
    )


def test_data_quality_detector_rejects_unrelated_error():
    assert not is_data_quality_failure(
        ValueError("Invalid file path")
    )


def test_configuration_detector_recognizes_invalid_parameter():
    assert is_configuration_failure(
        ValueError("The parameter must be positive")
    )


def test_configuration_detector_rejects_unrelated_error():
    assert not is_configuration_failure(
        ValueError("File not found")
    )


def test_dependency_detector_recognizes_missing_module():
    assert is_dependency_failure(
        ModuleNotFoundError("No module named 'fake_package'")
    )


def test_dependency_detector_recognizes_import_error():
    assert is_dependency_failure(
        ImportError("Cannot import required component")
    )


def test_dependency_detector_rejects_unrelated_error():
    assert not is_dependency_failure(
        ValueError("Incorrect data format")
    )
