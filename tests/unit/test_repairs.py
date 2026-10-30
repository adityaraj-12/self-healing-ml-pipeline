from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from healing.recovery.repair_executor import RepairExecutor
from healing.repair.repair_candidate import RepairCandidate
from healing.repair.repair_policy import enforce_repair_policy


@pytest.fixture
def executor():
    return RepairExecutor()


def test_valid_schema_repair(executor):
    data = pd.DataFrame({
        "mean_radius": [1.0, 2.0],
        "target": [0, 1],
    })
    original = data.copy(deep=True)

    candidate = {
        "action": "rename_column",
        "parameters": {
            "column_mapping": {
                "mean_radius": "mean radius"
            }
        },
    }

    repaired = executor.apply_schema_repair(data, candidate)

    assert "mean radius" in repaired.columns
    assert "mean_radius" not in repaired.columns
    assert repaired["mean radius"].tolist() == [1.0, 2.0]
    pd.testing.assert_frame_equal(data, original)


def test_schema_repair_rejects_missing_source(executor):
    data = pd.DataFrame({"feature": [1, 2]})

    candidate = {
        "action": "rename_column",
        "parameters": {
            "column_mapping": {"missing": "renamed"}
        },
    }

    with pytest.raises(ValueError, match="Source column not found"):
        executor.apply_schema_repair(data, candidate)


def test_schema_repair_rejects_existing_target(executor):
    data = pd.DataFrame({
        "old_name": [1, 2],
        "new_name": [3, 4],
    })

    candidate = {
        "action": "rename_column",
        "parameters": {
            "column_mapping": {"old_name": "new_name"}
        },
    }

    with pytest.raises(ValueError, match="Target column already exists"):
        executor.apply_schema_repair(data, candidate)


def test_schema_repair_rejects_unsupported_action(executor):
    data = pd.DataFrame({"feature": [1, 2]})

    candidate = {
        "action": "execute_code",
        "parameters": {},
    }

    with pytest.raises(ValueError, match="Unsupported schema repair action"):
        executor.apply_schema_repair(data, candidate)


def test_valid_configuration_repair_does_not_mutate_original(executor):
    config = {
        "model": {"C": 0.0, "max_iter": 100},
        "split": {"test_size": 0.2},
    }
    original = deepcopy(config)

    candidate = {
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "C",
                "observed_value": 0.0,
                "proposed_value": 1.0,
            }]
        },
    }

    repaired = executor.apply_configuration_repair(config, candidate)

    assert repaired["model"]["C"] == 1.0
    assert config == original
    assert repaired is not config


def test_configuration_repair_rejects_unsupported_parameter(executor):
    config = {"model": {"C": 1.0, "max_iter": 100}}

    candidate = {
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "random_state",
                "observed_value": None,
                "proposed_value": 42,
            }]
        },
    }

    with pytest.raises(ValueError, match="Unsupported configuration parameter"):
        executor.apply_configuration_repair(config, candidate)


def test_configuration_repair_rejects_nonpositive_c(executor):
    config = {"model": {"C": 0.0, "max_iter": 100}}

    candidate = {
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "C",
                "observed_value": 0.0,
                "proposed_value": -1.0,
            }]
        },
    }

    with pytest.raises(ValueError, match="C must be finite and positive"):
        executor.apply_configuration_repair(config, candidate)


def test_configuration_repair_rejects_noninteger_max_iter(executor):
    config = {"model": {"C": 1.0, "max_iter": 0}}

    candidate = {
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "max_iter",
                "observed_value": 0,
                "proposed_value": 2.5,
            }]
        },
    }

    with pytest.raises(ValueError, match="max_iter must be a positive integer"):
        executor.apply_configuration_repair(config, candidate)


def test_configuration_repair_rejects_stale_observed_value(executor):
    config = {"model": {"C": 0.0, "max_iter": 100}}

    candidate = {
        "action": "restore_configuration",
        "parameters": {
            "changes": [{
                "parameter": "C",
                "observed_value": -5.0,
                "proposed_value": 1.0,
            }]
        },
    }

    with pytest.raises(ValueError, match="changed unexpectedly"):
        executor.apply_configuration_repair(config, candidate)


def test_imputation_uses_training_median_and_preserves_inputs(executor):
    train = pd.DataFrame({"feature": [1.0, np.nan, 3.0]})
    test = pd.DataFrame({"feature": [np.nan, 100.0]})

    original_train = train.copy(deep=True)
    original_test = test.copy(deep=True)

    candidate = {
        "action": "impute_missing_values",
        "parameters": {},
    }

    repaired_train, repaired_test = executor.impute_training_test(
        train, test, candidate
    )

    assert repaired_train["feature"].tolist() == [1.0, 2.0, 3.0]
    assert repaired_test["feature"].tolist() == [2.0, 100.0]
    assert not repaired_train.isna().any().any()
    assert not repaired_test.isna().any().any()

    pd.testing.assert_frame_equal(train, original_train)
    pd.testing.assert_frame_equal(test, original_test)


def test_imputation_rejects_unsupported_action(executor):
    train = pd.DataFrame({"feature": [1.0, np.nan]})
    test = pd.DataFrame({"feature": [2.0]})

    candidate = {
        "action": "drop_all_rows",
        "parameters": {},
    }

    with pytest.raises(ValueError, match="Unsupported data-quality repair action"):
        executor.impute_training_test(train, test, candidate)


def test_imputation_rejects_entirely_missing_training_column(executor):
    train = pd.DataFrame({"feature": [np.nan, np.nan]})
    test = pd.DataFrame({"feature": [1.0]})

    candidate = {
        "action": "impute_missing_values",
        "parameters": {},
    }

    with pytest.raises(ValueError, match="No valid training imputation value"):
        executor.impute_training_test(train, test, candidate)


def test_policy_rejects_action_not_allowed_for_failure_type():
    candidate = {
        "failure_type": "data_quality",
        "action": "rename_column",
        "parameters": {},
    }

    with pytest.raises(ValueError, match="is not permitted"):
        enforce_repair_policy(candidate)


def test_policy_requires_approval_for_dependency_repair():
    candidate = {
        "failure_type": "dependency_error",
        "action": "verify_dependency",
        "requires_human_approval": False,
        "status": "draft",
    }
    original = deepcopy(candidate)

    repaired = enforce_repair_policy(candidate)

    assert repaired["requires_human_approval"] is True
    assert repaired["status"] == "proposed"
    assert candidate == original


def test_repair_candidate_serialization():
    incident = SimpleNamespace(
        incident_id="INC-TEST",
        failure_type="schema_change",
    )

    plan = {
        "action": "rename_column",
        "target": "input_schema",
        "parameters": {
            "column_mapping": {"old": "new"}
        },
        "rationale": "Restore the expected schema.",
        "evidence": ["Schema mismatch detected."],
        "validation_checks": ["Expected columns match."],
        "risks": [],
        "requires_human_approval": False,
    }

    candidate = RepairCandidate.create(incident, plan)
    result = candidate.to_dict()

    assert result["candidate_id"].startswith("RC-")
    assert result["incident_id"] == "INC-TEST"
    assert result["failure_type"] == "schema_change"
    assert result["action"] == "rename_column"
    assert result["status"] == "proposed"
    assert result["generator"] == "rule_based"
    assert result["parameters"] == plan["parameters"]


def test_planner_escalates_non_missing_data_quality_subtypes():
    from healing.rca.rule_based_rca import RuleBasedRCA
    from healing.repair.repair_planner import RepairPlanner

    incident = SimpleNamespace(
        failure_type="data_quality",
        error_message="Input matrix contains infinity values",
        to_dict=lambda: {},
    )
    rca = RuleBasedRCA().analyze(incident)

    candidate = RepairPlanner().plan(incident, rca)

    assert candidate["action"] == "manual_diagnosis"
    assert candidate["requires_human_approval"] is True
