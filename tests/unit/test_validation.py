
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from healing.validation.repair_validator import RepairValidator


def make_validator():
    # These tests exercise individual validation methods.
    # Avoid loading real configuration files unnecessarily.
    return RepairValidator.__new__(RepairValidator)


def test_rejects_schema_mapping_with_missing_source_column():
    validator = make_validator()
    checks = []

    workspace = {
        "data": pd.DataFrame({
            "mean_radius": [1.0, 2.0]
        })
    }

    candidate = {
        "failure_type": "schema_change",
        "action": "rename_column",
        "parameters": {
            "column_mapping": {
                "missing_column": "mean radius"
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="source_column_exists"
    ):
        validator._apply_schema_repair(
            workspace, candidate, checks
        )

    assert any(
        check["check"] == "source_column_exists:missing_column"
        and not check["passed"]
        for check in checks
    )


def test_rejects_non_positive_configuration_value():
    validator = make_validator()
    checks = []

    workspace = {
        "data": pd.DataFrame({
            "feature": [1.0, 2.0, 3.0, 4.0]
        }),
        "target": pd.Series([0, 1, 0, 1]),
        "config": {
            "model": {
                "C": 0.0,
                "max_iter": 100
            },
            "split": {
                "test_size": 0.25,
                "random_state": 42
            }
        }
    }

    candidate = {
        "failure_type": "configuration_error",
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "C",
                "observed_value": 0.0,
                "proposed_value": -1.0
            }]
        }
    }

    with pytest.raises(
        ValueError,
        match="valid_proposed_value:C"
    ):
        validator._apply_configuration_repair(
            workspace, candidate, checks
        )

    assert workspace["config"]["model"]["C"] == 0.0


def test_rejects_unsupported_configuration_parameter():
    validator = make_validator()
    checks = []

    workspace = {
        "data": pd.DataFrame({"feature": [1.0, 2.0]}),
        "target": pd.Series([0, 1]),
        "config": {
            "model": {"C": 0.0, "max_iter": 100},
            "split": {
                "test_size": 0.5,
                "random_state": 42
            }
        }
    }

    candidate = {
        "failure_type": "configuration_error",
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "unapproved_setting",
                "observed_value": None,
                "proposed_value": 123
            }]
        }
    }

    with pytest.raises(
        ValueError,
        match="supported_parameter:unapproved_setting"
    ):
        validator._apply_configuration_repair(
            workspace, candidate, checks
        )


def test_rejects_candidate_with_mismatched_action():
    validator = make_validator()

    candidate = {
        "failure_type": "data_quality",
        "action": "rename_column",
        "parameters": {}
    }

    result = validator._validate_candidate(
        {}, candidate, []
    )

    assert result["status"] == "rejected"
    assert "not allowed" in result["reason"]


def test_rejects_data_repair_if_missing_values_remain(
    monkeypatch
):
    validator = make_validator()
    checks = []

    workspace = {
        "data": pd.DataFrame({
            "feature": [
                1.0, np.nan, 3.0, 4.0,
                5.0, 6.0, 7.0, 8.0,
                9.0, 10.0, 11.0, 12.0
            ]
        }),
        "target": pd.Series([0, 1] * 6),
        "config": {
            "split": {
                "test_size": 0.33,
                "random_state": 42
            },
            "model": {
                "C": 1.0,
                "max_iter": 100
            }
        }
    }

    candidate = {
        "failure_type": "data_quality",
        "action": "impute_missing_values",
        "parameters": {
            "column_scope": "columns_with_missing_values",
            "numeric_strategy": "median",
            "categorical_strategy": "most_frequent",
            "exclude_target_column": True,
        },
    }

    # Simulate an imputation operation that fails to fill NaNs.
    monkeypatch.setattr(
        pd.Series,
        "fillna",
        lambda self, *args, **kwargs: self
    )

    with pytest.raises(
        ValueError,
        match="no_missing_feature_values"
    ):
        validator._apply_data_quality_repair(
            workspace, candidate, checks
        )

    assert any(
        check["check"] == "no_missing_feature_values"
        and not check["passed"]
        for check in checks
    )


@pytest.mark.parametrize(
    ("candidate_incident_id", "candidate_failure_type", "expected_reason"),
    [
        ("INC-OTHER", "data_quality", "incident_id"),
        ("INC-TEST", "schema_change", "failure_type"),
    ],
)
def test_validator_rejects_candidate_identity_mismatch(
    candidate_incident_id,
    candidate_failure_type,
    expected_reason,
):
    validator = make_validator()

    candidate = {
        "candidate_id": "RC-CROSS-INCIDENT",
        "incident_id": candidate_incident_id,
        "failure_type": candidate_failure_type,
        "action": "impute_missing_values",
        "parameters": {},
    }

    incident = SimpleNamespace(
        incident_id="INC-TEST",
        failure_type="data_quality",
    )

    report = validator.validate(candidate, incident)

    assert report["status"] == "rejected"
    assert expected_reason in report["reason"]
    assert report["candidate_id"] == candidate["candidate_id"]
    assert report["incident_id"] == incident.incident_id


def test_dependency_repair_requires_human_approval():
    validator = make_validator()

    candidate = {
        "candidate_id": "RC-TEST",
        "incident_id": "INC-TEST",
        "failure_type": "dependency_error",
        "action": "verify_dependency"
    }

    incident = SimpleNamespace(
        incident_id="INC-TEST",
        failure_type="dependency_error",
    )

    report = validator.validate(candidate, incident)

    assert report["status"] == "needs_human_approval"
    assert "Dependency remediation" in report["reason"]


def test_rejects_data_repair_with_unapproved_strategy():
    validator = make_validator()
    checks = []
    workspace = {
        "data": pd.DataFrame({"feature": [1.0, np.nan, 3.0, 4.0]}),
        "target": pd.Series([0, 1, 0, 1]),
        "config": {
            "split": {"test_size": 0.5, "random_state": 42},
            "model": {"C": 1.0, "max_iter": 100},
        },
    }
    candidate = {
        "failure_type": "data_quality",
        "action": "impute_missing_values",
        "parameters": {
            "column_scope": "all_columns",
            "numeric_strategy": "drop",
            "categorical_strategy": "most_frequent",
            "exclude_target_column": False,
        },
    }

    with pytest.raises(ValueError, match="permitted_column_scope"):
        validator._apply_data_quality_repair(workspace, candidate, checks)

    assert checks[0]["check"] == "no_unrecognized_data_parameter_fields"
    assert checks[0]["passed"] is True
    assert any(check["check"] == "permitted_column_scope" and not check["passed"] for check in checks)


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("fill_target", True),
        ("execute_code", "print(1)"),
        ("allow_train_test_leakage", True),
    ],
)
def test_rejects_unrecognized_data_repair_parameter_fields(extra_field, extra_value):
    validator = make_validator()
    checks = []
    workspace = {
        "data": pd.DataFrame({"feature": [1.0, np.nan, 3.0, 4.0]}),
        "target": pd.Series([0, 1, 0, 1]),
        "config": {"split": {"test_size": 0.5, "random_state": 42}, "model": {"C": 1.0, "max_iter": 100}},
    }
    parameters = {
        "column_scope": "columns_with_missing_values",
        "numeric_strategy": "median",
        "categorical_strategy": "most_frequent",
        "exclude_target_column": True,
        extra_field: extra_value,
    }
    candidate = {"failure_type": "data_quality", "action": "impute_missing_values", "parameters": parameters}
    with pytest.raises(ValueError, match="no_unrecognized_data_parameter_fields"):
        validator._apply_data_quality_repair(workspace, candidate, checks)
    assert checks[0]["check"] == "no_unrecognized_data_parameter_fields"
    assert checks[0]["passed"] is False


def test_rejects_extra_field_inside_configuration_change():
    validator = make_validator()
    checks = []
    workspace = {
        "data": pd.DataFrame({"feature": [1.0, 2.0, 3.0, 4.0]}),
        "target": pd.Series([0, 1, 0, 1]),
        "config": {"model": {"C": 0.0, "max_iter": 100}, "split": {"test_size": 0.5, "random_state": 42}},
    }
    candidate = {
        "failure_type": "configuration_error",
        "action": "restore_configuration",
        "parameters": {"changes": [{"parameter": "C", "observed_value": 0.0, "proposed_value": 1.0, "execute_code": "print(1)"}]},
    }
    with pytest.raises(ValueError, match="no_unrecognized_configuration_change_fields"):
        validator._apply_configuration_repair(workspace, candidate, checks)
    assert any(check["check"] == "no_unrecognized_configuration_change_fields" and not check["passed"] for check in checks)


def test_rejects_extra_top_level_configuration_parameter_field():
    validator = make_validator()
    checks = []
    workspace = {
        "data": pd.DataFrame({"feature": [1.0, 2.0, 3.0, 4.0]}),
        "target": pd.Series([0, 1, 0, 1]),
        "config": {"model": {"C": 0.0, "max_iter": 100}, "split": {"test_size": 0.5, "random_state": 42}},
    }
    candidate = {
        "failure_type": "configuration_error",
        "action": "restore_configuration",
        "parameters": {"changes": [{"parameter": "C", "observed_value": 0.0, "proposed_value": 1.0}], "execute_code": "print(1)"},
    }
    with pytest.raises(ValueError, match="no_unrecognized_configuration_parameter_fields"):
        validator._apply_configuration_repair(workspace, candidate, checks)
    assert checks[0]["check"] == "no_unrecognized_configuration_parameter_fields"
    assert checks[0]["passed"] is False


def test_rejects_unrecognized_schema_repair_parameter_field():
    validator = make_validator()
    checks = []
    workspace = {"data": pd.DataFrame({"mean_radius": [1.0, 2.0]})}
    candidate = {
        "failure_type": "schema_change",
        "action": "rename_column",
        "parameters": {
            "column_mapping": {"mean_radius": "mean radius"},
            "execute_code": "print(1)",
        },
    }
    with pytest.raises(ValueError, match="no_unrecognized_schema_parameter_fields"):
        validator._apply_schema_repair(workspace, candidate, checks)
    assert checks[0]["check"] == "no_unrecognized_schema_parameter_fields"
    assert checks[0]["passed"] is False
