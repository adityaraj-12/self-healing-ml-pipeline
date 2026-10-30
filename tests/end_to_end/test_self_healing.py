import numpy as np
from pathlib import Path
from types import SimpleNamespace

import healing.recovery.recovery_engine as recovery_module
import healing.validation.repair_validator as validation_module

from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.repair.repair_policy import enforce_repair_policy
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine


def test_data_quality_failure_is_validated_and_recovered(
    monkeypatch, tmp_path
):
    # Load configuration while the current directory is the project root.
    validator = RepairValidator()
    engine = RecoveryEngine()

    # Redirect recovery artifacts to a temporary directory.
    monkeypatch.chdir(tmp_path)

    def inject_one_missing_value(failure_type, x, config):
        changed = x.copy(deep=True)

        if failure_type == "data_quality":
            changed.iloc[0, 0] = np.nan

        return changed, config

    # Use the same deterministic failure for validation and recovery.
    monkeypatch.setattr(
        validation_module,
        "inject_failure",
        inject_one_missing_value,
    )
    monkeypatch.setattr(
        recovery_module,
        "inject_failure",
        inject_one_missing_value,
    )

    incident = SimpleNamespace(
        incident_id="INC-END-TO-END",
        failure_type="data_quality",
        error_message="Input contains NaN values",
        context={
            "failure_injection": {
                "parameters": {
                    "fraction": 0.05,
                    "random_seed": 42,
                }
            }
        },
    )

    rca = RuleBasedRCA().analyze(incident)

    candidate = enforce_repair_policy(
        RepairGenerator().generate(
            incident,
            rca,
        ).to_dict()
    )

    report = validator.validate(candidate, incident)

    assert report["status"] == "passed"
    assert report["candidate_id"] == candidate["candidate_id"]

    result = engine.recover(
        incident,
        candidate,
        report,
    )

    assert result["status"] == "recovered"
    assert result["post_recovery_check"]["model_reload_successful"]
    assert result["post_recovery_check"]["predictions_identical"]
    assert result["post_recovery_check"]["metrics_identical"]

    assert Path(result["model_path"]).is_file()
    assert Path(result["metrics_path"]).is_file()


def test_schema_change_failure_is_validated_and_recovered(
    monkeypatch, tmp_path
):
    from pathlib import Path
    from types import SimpleNamespace

    from healing.rca.rule_based_rca import RuleBasedRCA
    from healing.repair.repair_generator import RepairGenerator
    from healing.repair.repair_policy import enforce_repair_policy
    from healing.validation.repair_validator import RepairValidator
    from healing.recovery.recovery_engine import RecoveryEngine

    project_root = Path.cwd()
    validator = RepairValidator()
    engine = RecoveryEngine()

    schema_path = Path(validator.schema_path)
    if not schema_path.is_absolute():
        schema_path = (project_root / schema_path).resolve()

    assert schema_path.is_file(), (
        f"Baseline schema not found: {schema_path}"
    )

    # Keep the baseline schema accessible after isolating artifacts.
    validator.schema_path = str(schema_path)
    validator.pipeline_config["artifacts"]["schema"] = str(schema_path)
    engine.pipeline_config["artifacts"]["schema"] = str(schema_path)

    monkeypatch.chdir(tmp_path)

    incident = SimpleNamespace(
        incident_id="INC-SCHEMA-E2E",
        failure_type="schema_change",
        error_message=(
            "Schema mismatch | missing=['mean radius'] "
            "| unexpected=['mean_radius']"
        ),
        pipeline_config={},
        context={
            "failure_injection": {
                "parameters": {
                    "original_column": "mean radius",
                    "replacement_column": "mean_radius",
                }
            }
        },
    )

    rca = RuleBasedRCA().analyze(incident)
    candidate = enforce_repair_policy(
        RepairGenerator().generate(incident, rca).to_dict()
    )

    report = validator.validate(candidate, incident)

    assert report["status"] == "passed", report

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "recovered", result
    assert result["post_recovery_check"]["model_reload_successful"]
    assert result["post_recovery_check"]["predictions_identical"]
    assert result["post_recovery_check"]["metrics_identical"]
    assert Path(result["model_path"]).is_file()
    assert Path(result["metrics_path"]).is_file()


def test_configuration_failure_is_validated_and_recovered(
    monkeypatch, tmp_path
):
    from pathlib import Path
    from types import SimpleNamespace

    from healing.rca.rule_based_rca import RuleBasedRCA
    from healing.repair.repair_generator import RepairGenerator
    from healing.repair.repair_policy import enforce_repair_policy
    from healing.validation.repair_validator import RepairValidator
    from healing.recovery.recovery_engine import RecoveryEngine

    validator = RepairValidator()
    engine = RecoveryEngine()

    healthy_c = validator.pipeline_config["model"]["C"]
    healthy_max_iter = validator.pipeline_config["model"]["max_iter"]

    monkeypatch.chdir(tmp_path)

    incident = SimpleNamespace(
        incident_id="INC-CONFIG-E2E",
        failure_type="configuration_error",
        error_message="The 'C' parameter must be a positive float",
        # The planner compares this failed model config with baseline.
        pipeline_config={
            "C": 0.0,
            "max_iter": healthy_max_iter,
        },
        context={
            "baseline_config": {
                "model": {
                    "C": healthy_c,
                    "max_iter": healthy_max_iter,
                }
            },
            "failure_injection": {
                "parameters": {
                    "parameter": "C",
                    "invalid_value": 0.0,
                }
            },
        },
    )

    rca = RuleBasedRCA().analyze(incident)
    candidate = enforce_repair_policy(
        RepairGenerator().generate(incident, rca).to_dict()
    )

    assert candidate["action"] == "restore_configuration"
    assert candidate["parameters"]["changes"]

    report = validator.validate(candidate, incident)

    assert report["status"] == "passed", report

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "recovered", result
    assert result["post_recovery_check"]["model_reload_successful"]
    assert result["post_recovery_check"]["predictions_identical"]
    assert result["post_recovery_check"]["metrics_identical"]
    assert Path(result["model_path"]).is_file()
    assert Path(result["metrics_path"]).is_file()


def test_dependency_failure_remains_under_human_review(
    monkeypatch, tmp_path
):
    from pathlib import Path
    from types import SimpleNamespace

    from healing.rca.rule_based_rca import RuleBasedRCA
    from healing.repair.repair_generator import RepairGenerator
    from healing.repair.repair_policy import enforce_repair_policy
    from healing.validation.repair_validator import RepairValidator
    from healing.recovery.recovery_engine import RecoveryEngine

    validator = RepairValidator()
    engine = RecoveryEngine()
    monkeypatch.chdir(tmp_path)

    incident = SimpleNamespace(
        incident_id="INC-DEPENDENCY-E2E",
        failure_type="dependency_error",
        error_message="No module named 'fake_missing_package'",
        pipeline_config={},
        context={
            "failure_injection": {
                "parameters": {
                    "module": "fake_missing_package",
                }
            }
        },
    )

    rca = RuleBasedRCA().analyze(incident)
    candidate = enforce_repair_policy(
        RepairGenerator().generate(incident, rca).to_dict()
    )

    assert candidate["requires_human_approval"] is True

    report = validator.validate(candidate, incident)

    assert report["status"] == "needs_human_approval"

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "needs_human_approval"
    assert not (
        Path("artifacts/recovered").exists()
    ), "No automatic recovery artifacts should be created."
