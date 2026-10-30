import json

import pandas as pd
import pytest

import pipeline.runner as runner


def test_pipeline_records_incident_and_rca_on_schema_failure(
    monkeypatch, tmp_path
):
    artifacts = {
        "log": str(tmp_path / "pipeline.log"),
        "incidents": str(tmp_path / "incidents.jsonl"),
        "rca": str(tmp_path / "rca.jsonl"),
        "schema": str(tmp_path / "schema.json"),
        "metrics": str(tmp_path / "metrics.json"),
        "model": str(tmp_path / "model.joblib"),
    }

    config = {
        "model": {"C": 1.0, "max_iter": 100},
        "split": {"test_size": 0.25, "random_state": 42},
        "artifacts": artifacts,
    }

    failure_config = {
        "failures": {
            "schema_change": {"enabled": True}
        }
    }

    monkeypatch.setattr(runner, "load_config", lambda: config)
    monkeypatch.setattr(
        runner, "load_failure_config", lambda: failure_config
    )
    monkeypatch.setattr(runner, "setup_logging", lambda path: None)

    monkeypatch.setattr(
        runner,
        "load_data",
        lambda: (
            pd.DataFrame({"feature": [1.0, 2.0, 3.0]}),
            pd.Series([0, 1, 0]),
        ),
    )

    def inject_schema_change(failure_type, x, config):
        if failure_type == "schema_change":
            return x.rename(
                columns={"feature": "feature_renamed"}
            ), config
        return x, config

    def fail_schema_validation(x, schema_path):
        raise ValueError(
            "Schema mismatch | missing=['feature'] "
            "| unexpected=['feature_renamed']"
        )

    monkeypatch.setattr(
        runner, "inject_failure", inject_schema_change
    )
    monkeypatch.setattr(
        runner, "validate_schema", fail_schema_validation
    )

    # The pipeline intentionally re-raises after recording the failure.
    with pytest.raises(ValueError, match="Schema mismatch"):
        runner.run_pipeline(failure_type="schema_change")

    incident_lines = (
        tmp_path / "incidents.jsonl"
    ).read_text(encoding="utf-8").splitlines()

    rca_lines = (
        tmp_path / "rca.jsonl"
    ).read_text(encoding="utf-8").splitlines()

    assert incident_lines
    assert rca_lines

    incident = json.loads(incident_lines[-1])
    rca = json.loads(rca_lines[-1])

    assert incident["failure_type"] == "schema_change"
    assert incident["stage"] == "schema_validation"
    assert rca["failure_type"] == "schema_change"
    assert rca["root_cause_code"] == (
        "schema_rename:feature_renamed->feature"
    )


def test_pipeline_records_uninjected_runtime_failure(monkeypatch, tmp_path):
    """A non-injected runtime error should be logged as an unknown failure."""
    artifacts = {
        "log": str(tmp_path / "logs" / "pipeline.log"),
        "incidents": str(tmp_path / "incidents" / "incidents.jsonl"),
        "rca": str(tmp_path / "incidents" / "rca.jsonl"),
        "schema": str(tmp_path / "schemas" / "schema.json"),
        "metrics": str(tmp_path / "metrics" / "metrics.json"),
        "model": str(tmp_path / "models" / "model.joblib"),
    }
    config = {
        "model": {"C": 1.0, "max_iter": 100},
        "split": {"test_size": 0.25, "random_state": 42},
        "artifacts": artifacts,
    }
    monkeypatch.setattr(runner, "load_config", lambda: config)
    monkeypatch.setattr(
        runner,
        "load_failure_config",
        lambda: {"failures": {"schema_change": {"enabled": True}}},
    )
    monkeypatch.setattr(runner, "setup_logging", lambda path: None)

    def fail_during_load():
        raise TimeoutError("synthetic load timeout without a fault injection")

    monkeypatch.setattr(runner, "load_data", fail_during_load)

    with pytest.raises(TimeoutError, match="synthetic load timeout"):
        runner.run_pipeline(auto_heal=False)

    incident_rows = [
        json.loads(line)
        for line in (tmp_path / "incidents" / "incidents.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    assert incident_rows
    assert incident_rows[-1]["failure_type"] == "unknown_runtime_failure"
    assert incident_rows[-1]["context"]["failure_injection"]["ground_truth"] == {}


def test_healthy_pipeline_creates_model_artifact_parent(monkeypatch, tmp_path):
    """A clean checkout should not need a pre-existing artifacts/models folder."""
    artifacts = {
        "log": str(tmp_path / "logs" / "pipeline.log"),
        "incidents": str(tmp_path / "incidents" / "incidents.jsonl"),
        "rca": str(tmp_path / "incidents" / "rca.jsonl"),
        "schema": str(tmp_path / "schemas" / "schema.json"),
        "metrics": str(tmp_path / "metrics" / "metrics.json"),
        "model": str(tmp_path / "missing" / "nested" / "models" / "model.joblib"),
    }
    config = {
        "model": {"C": 1.0, "max_iter": 100},
        "split": {"test_size": 0.25, "random_state": 42},
        "artifacts": artifacts,
    }
    monkeypatch.setattr(runner, "load_config", lambda: config)
    monkeypatch.setattr(
        runner,
        "load_failure_config",
        lambda: {"failures": {"schema_change": {"enabled": True}}},
    )
    monkeypatch.setattr(runner, "setup_logging", lambda path: None)
    monkeypatch.setattr(
        runner,
        "load_data",
        lambda: (
            pd.DataFrame({"feature": [1.0, 2.0, 3.0, 4.0]}),
            pd.Series([0, 1, 0, 1]),
        ),
    )
    monkeypatch.setattr(
        runner,
        "split_data",
        lambda x, y, test_size, random_state: (
            pd.DataFrame({"feature": [1.0, 2.0]}),
            pd.DataFrame({"feature": [3.0, 4.0]}),
            pd.Series([0, 1]),
            pd.Series([0, 1]),
        ),
    )
    monkeypatch.setattr(
        runner, "train_model", lambda x, y, C, max_iter: {"model": "test-double"}
    )
    monkeypatch.setattr(
        runner, "evaluate_model", lambda model, x, y: {"accuracy": 0.5}
    )

    runner.run_pipeline(auto_heal=False)

    model_path = tmp_path / "missing" / "nested" / "models" / "model.joblib"
    assert model_path.is_file()
    assert (tmp_path / "metrics" / "metrics.json").is_file()
