from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json

import numpy as np
import yaml

from failures.injector import inject_failure
from pipeline.ingestion import load_data
from pipeline.preprocessing import split_data
from pipeline.training import train_model
from pipeline.evaluation import evaluate_model
from pipeline.schema_validation import load_schema

from healing.validation.sandbox import RepairSandbox

import pandas as pd

from healing.recovery.repair_executor import RepairExecutor


class RepairValidator:

    def __init__(self):
        self.sandbox = RepairSandbox()

        with open("configs/pipeline.yaml", "r") as f:
            self.pipeline_config = yaml.safe_load(f)

        with open("configs/failures.yaml", "r") as f:
            self.failure_config = yaml.safe_load(f)

        self.schema_path = self.pipeline_config[
            "artifacts"
        ]["schema"]

    def _check(self, checks, name, condition, details=""):
        passed = bool(condition)

        checks.append({
            "check": name,
            "passed": passed,
            "details": details
        })

        if not passed:
            raise ValueError(
                f"Validation check failed: {name}. {details}"
            )

    def _load_workspace(self, incident):
        x, y = load_data()

        config = deepcopy(self.pipeline_config)
        config["failures"] = deepcopy(
            self.failure_config["failures"]
        )

        injection = incident.context.get(
            "failure_injection", {}
        )

        parameters = injection.get("parameters", {})
        failure_type = incident.failure_type

        if failure_type in config["failures"]:
            config["failures"][failure_type] = {
                **config["failures"][failure_type],
                **parameters
            }

        return x, y, config

    def _apply_schema_repair(self, workspace, candidate, checks):
        params = candidate["parameters"]
        allowed_parameter_keys = {"column_mapping", "semantic_equivalence_required"}
        self._check(
            checks,
            "no_unrecognized_schema_parameter_fields",
            isinstance(params, dict) and set(params).issubset(allowed_parameter_keys),
            f"Unexpected schema parameter fields: {sorted(set(params) - allowed_parameter_keys) if isinstance(params, dict) else 'parameters_not_object'}",
        )
        mapping = params.get("column_mapping", {})

        x = workspace["data"]

        self._check(
            checks,
            "schema_mapping_present",
            bool(mapping),
            "A column mapping must be specified."
        )

        # Verify each rename is possible.
        for source, target in mapping.items():
            self._check(
                checks,
                f"source_column_exists:{source}",
                source in x.columns,
                f"Source column: {source}"
            )

            self._check(
                checks,
                f"target_column_missing:{target}",
                target not in x.columns,
                f"Target column: {target}"
            )

        original_rows = len(x)
        original_values = x.copy(deep=True)

        # Controlled column renaming; no generated code execution.
        x = x.rename(columns=mapping, errors="raise")

        expected = load_schema(self.schema_path)

        self._check(
            checks,
            "expected_column_order",
            list(x.columns) == expected["columns"],
            "Repaired columns must match the original schema order."
        )

        actual_dtypes = {
            col: str(dtype)
            for col, dtype in x.dtypes.items()
        }

        self._check(
            checks,
            "expected_column_types",
            actual_dtypes == expected["dtypes"],
            "Repaired column types must match the recorded schema."
        )

        self._check(
            checks,
            "row_count_preserved",
            len(x) == original_rows,
            "Schema repair must not add or remove rows."
        )

        self._check(
            checks,
            "column_values_preserved",
            all(
                x[target].equals(original_values[source])
                for source, target in mapping.items()
            ),
            "A rename must preserve the original column values."
        )

        workspace["data"] = x

    
    def _apply_data_quality_repair(
        self, workspace, candidate, checks
    ):
        # Recheck the complete data-repair contract at the validator boundary.
        # The executor does not execute arbitrary candidate code, but silently
        # ignoring a proposal's unsupported strategy fields would make the
        # recorded proposal disagree with the repair actually applied.
        parameters = candidate.get("parameters", {})
        allowed_parameter_keys = {
            "column_scope", "numeric_strategy", "categorical_strategy", "exclude_target_column"
        }
        self._check(
            checks,
            "no_unrecognized_data_parameter_fields",
            isinstance(parameters, dict) and set(parameters).issubset(allowed_parameter_keys),
            f"Unexpected data-repair parameter fields: {sorted(set(parameters) - allowed_parameter_keys) if isinstance(parameters, dict) else 'parameters_not_object'}",
        )
        self._check(
            checks,
            "permitted_column_scope",
            parameters.get("column_scope") == "columns_with_missing_values",
            "Data repair must target only columns with missing feature values."
        )
        self._check(
            checks,
            "permitted_numeric_strategy",
            parameters.get("numeric_strategy") == "median",
            "Numeric imputation must use the allowlisted median strategy."
        )
        self._check(
            checks,
            "permitted_categorical_strategy",
            parameters.get("categorical_strategy") == "most_frequent",
            "Categorical imputation must use the allowlisted most-frequent strategy."
        )
        self._check(
            checks,
            "target_column_excluded",
            parameters.get("exclude_target_column") is True,
            "The target column must be excluded from feature imputation."
        )

        x = workspace["data"]
        y = workspace["target"]
        config = workspace["config"]

        original_rows = len(x)
        original_columns = list(x.columns)

        missing_before = int(x.isna().sum().sum())

        self._check(
            checks,
            "missing_values_present",
            missing_before > 0,
            "The injected dataset must contain missing values."
        )

        # Split before imputation. Never use test data to fit
        # imputation values.
        x_train, x_test, y_train, y_test = split_data(
            x,
            y,
            test_size=config["split"]["test_size"],
            random_state=config["split"]["random_state"]
        )

        # Use the same allowlisted executor as real recovery.
        try:
            x_train, x_test = RepairExecutor().impute_training_test(
                x_train,
                x_test,
                candidate
            )
        except ValueError:
            missing_after = (
                int(x_train.isna().sum().sum())
                + int(x_test.isna().sum().sum())
            )

            if missing_after > 0:
                self._check(
                    checks,
                    "no_missing_feature_values",
                    False,
                    f"Missing values remain after attempted repair: "
                    f"{missing_after}"
                )

            raise

        missing_after = (
            int(x_train.isna().sum().sum())
            + int(x_test.isna().sum().sum())
        )

        self._check(
            checks,
            "no_missing_feature_values",
            missing_after == 0,
            f"Missing values before={missing_before}, "
            f"after={missing_after}"
        )

        self._check(
            checks,
            "row_count_preserved",
            len(x_train) + len(x_test) == original_rows,
            "Imputation must not add or remove rows."
        )

        schema_preserved = (
            list(x_train.columns) == original_columns
            and list(x_test.columns) == original_columns
        )

        self._check(
            checks,
            "column_schema_preserved",
            schema_preserved,
            "Training and test features must retain the original columns."
        )

        # Reconstruct the repaired feature data without changing
        # original row order.
        x_repaired = pd.concat(
            [x_train, x_test]
        ).sort_index()

        y_repaired = pd.concat(
            [y_train, y_test]
        ).sort_index()

        target_unchanged = y_repaired.equals(y.sort_index())

        self._check(
            checks,
            "target_unchanged",
            target_unchanged,
            "Feature imputation must not change target values."
        )

        # Test whether the repaired training data can train and evaluate
        # the configured model inside the sandbox.
        model = train_model(
            x_train,
            y_train,
            C=config["model"]["C"],
            max_iter=config["model"]["max_iter"]
        )

        metrics = evaluate_model(
            model,
            x_test,
            y_test
        )

        self._check(
            checks,
            "training_completed",
            True,
            "Model training and evaluation completed after imputation."
        )

        self._check(
            checks,
            "finite_evaluation_metrics",
            all(np.isfinite(value) for value in metrics.values()),
            json.dumps(metrics)
        )

        workspace["data"] = x_repaired
        workspace["target"] = y_repaired


    def _apply_configuration_repair(
        self, workspace, candidate, checks
    ):
        parameters = candidate.get("parameters", {})
        self._check(
            checks,
            "no_unrecognized_configuration_parameter_fields",
            isinstance(parameters, dict) and set(parameters) == {"changes"},
            f"Configuration repair accepts only the 'changes' field; received {sorted(parameters) if isinstance(parameters, dict) else 'parameters_not_object'}.",
        )
        changes = parameters.get("changes", [])

        config = workspace["config"]

        self._check(
            checks,
            "configuration_changes_present",
            bool(changes),
            "A specific parameter change is required."
        )

        for change in changes:
            self._check(
                checks,
                "no_unrecognized_configuration_change_fields",
                isinstance(change, dict) and set(change) == {"parameter", "observed_value", "proposed_value"},
                f"Configuration change must contain only parameter, observed_value, and proposed_value; received {sorted(change) if isinstance(change, dict) else 'change_not_object'}.",
            )
            param = change["parameter"]
            expected_current = change["observed_value"]
            proposed = change["proposed_value"]


            # Only permit explicitly supported model parameters.
            allowed_parameters = {"C", "max_iter"}

            self._check(
                checks,
                f"supported_parameter:{param}",
                param in allowed_parameters,
                f"Unsupported configuration parameter: {param}"
            )

            # Enforce safe value constraints before training.
            if param == "C":
                is_numeric = (
                    isinstance(proposed, (int, float, np.integer, np.floating))
                    and not isinstance(proposed, (bool, np.bool_))
                )

                valid_value = (
                    is_numeric
                    and np.isfinite(float(proposed))
                    and float(proposed) > 0
                )

                details = "C must be finite and strictly positive."

            else:  # max_iter
                valid_value = (
                    isinstance(proposed, (int, np.integer))
                    and not isinstance(proposed, (bool, np.bool_))
                    and proposed > 0
                )

                details = "max_iter must be a positive integer."

            self._check(
                checks,
                f"valid_proposed_value:{param}",
                valid_value,
                details
            )


            actual_current = config["model"].get(param)

            self._check(
                checks,
                f"current_value_matches:{param}",
                actual_current == expected_current,
                "The candidate must match the known failed "
                "configuration, not an unrelated configuration."
            )

            config["model"][param] = proposed

        # Test actual model execution with the proposed settings.
        x = workspace["data"]
        y = workspace["target"]

        x_train, x_test, y_train, y_test = split_data(
            x,
            y,
            test_size=config["split"]["test_size"],
            random_state=config["split"]["random_state"]
        )

        model = train_model(
            x_train,
            y_train,
            C=config["model"]["C"],
            max_iter=config["model"]["max_iter"]
        )

        metrics = evaluate_model(
            model,
            x_test,
            y_test
        )

        self._check(
            checks,
            "training_completed",
            True,
            "Model fit and evaluation completed."
        )

        self._check(
            checks,
            "finite_evaluation_metrics",
            all(
                np.isfinite(value)
                for value in metrics.values()
            ),
            json.dumps(metrics)
        )

        workspace["config"] = config

    def _validate_candidate(self, workspace, candidate, checks):
        failure_type = candidate["failure_type"]
        action = candidate["action"]


        expected_actions = {
            "schema_change": "rename_column",
            "data_quality": "impute_missing_values",
            "configuration_error": "restore_configuration",
            "dependency_error": "verify_dependency",
        }

        expected_action = expected_actions.get(failure_type)

        if expected_action is None:
            return {
                "status": "rejected",
                "reason": f"Unsupported failure type: {failure_type}"
            }

        if action != expected_action:
            return {
                "status": "rejected",
                "reason": (
                    f"Action {action!r} is not allowed for "
                    f"failure type {failure_type!r}; "
                    f"expected {expected_action!r}."
                )
            }


        if failure_type == "schema_change":
            self._apply_schema_repair(
                workspace, candidate, checks
            )

        elif failure_type == "data_quality":
            self._apply_data_quality_repair(
                workspace, candidate, checks
            )

        elif failure_type == "configuration_error":
            self._apply_configuration_repair(
                workspace, candidate, checks
            )

        elif failure_type == "dependency_error":
            # Never install or modify dependencies automatically.
            return {
                "status": "needs_human_approval",
                "reason": (
                    "Dependency repair requires environment and "
                    "package-manifest inspection. No packages were "
                    "installed or changed."
                )
            }

        else:
            return {
                "status": "rejected",
                "reason": (
                    f"Unsupported failure type: {failure_type}"
                )
            }

        return {
            "status": "passed",
            "reason": "All applicable sandbox checks passed."
        }

    def validate(self, candidate, incident):
        start = perf_counter()
        checks = []

        report = {
            "candidate_id": candidate["candidate_id"],
            "incident_id": incident.incident_id,
            "failure_type": candidate["failure_type"],
            "action": candidate["action"],
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "checks": checks
        }

        # Dependency remediation is explicitly guarded.
        if candidate["failure_type"] == "dependency_error":
            report.update({
                "status": "needs_human_approval",
                "reason": (
                    "The environment was not modified. "
                    "Dependency remediation needs review."
                )
            })
            report["duration_seconds"] = (
                perf_counter() - start
            )
            return report

        x, y, config = self._load_workspace(incident)

        # Store target separately; the pipeline config itself
        # is copied again inside the isolated workspace.
        try:
            with self.sandbox.create(x, config) as workspace:
                workspace["target"] = y.copy(deep=True)

                # Recreate the selected failure inside the sandbox.
                failure_type = candidate["failure_type"]

                if failure_type in {
                    "schema_change",
                    "data_quality",
                    "configuration_error"
                }:
                    changed_x, changed_config = inject_failure(
                        failure_type,
                        workspace["data"],
                        workspace["config"]
                    )

                    workspace["data"] = changed_x
                    workspace["config"] = changed_config

                result = self._validate_candidate(
                    workspace,
                    candidate,
                    checks
                )

                report.update(result)

        except Exception as exc:
            report.update({
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}"
            })

        report["duration_seconds"] = (
            perf_counter() - start
        )

        return report

    def save_report(self, report, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report) + "\n")