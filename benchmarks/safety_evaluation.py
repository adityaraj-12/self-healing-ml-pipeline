"""Expanded, deterministic evaluation of repair-validator guardrails.

The cases are programmatically generated across supported fault families. They
are targeted regression cases, not independent draws from a real-world attack
population; rates must not be interpreted as production safety probabilities.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

from healing.validation.repair_validator import RepairValidator
from pipeline.ingestion import load_data
from pipeline.schema_validation import save_schema

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"


def load_yaml(path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_incident(case_id, failure_type, parameters, message):
    return SimpleNamespace(
        incident_id=f"SAFETY-{case_id.upper()}",
        failure_type=failure_type,
        error_message=message,
        context={
            "failure_injection": {
                "parameters": parameters,
                "ground_truth": {},
            }
        },
    )


def make_candidate(case_id, incident, action, parameters):
    return {
        "candidate_id": f"RC-SAFETY-{case_id.upper()}",
        "incident_id": incident.incident_id,
        "failure_type": incident.failure_type,
        "action": action,
        "target": "safety_evaluation",
        "parameters": parameters,
        "requires_human_approval": incident.failure_type == "dependency_error",
        "status": "proposed",
    }


def ensure_baseline_schema(pipeline_cfg):
    """Create the expected schema file if this is a clean checkout."""
    schema_path = Path(pipeline_cfg["artifacts"]["schema"])
    if not schema_path.is_absolute():
        schema_path = ROOT / schema_path
    if not schema_path.exists():
        x, _ = load_data()
        save_schema(x, schema_path)


def wilson_interval(successes, total, z=1.959963984540054):
    """Return a two-sided Wilson score interval, or None for no trials."""
    if total <= 0:
        return None
    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    half = z * math.sqrt((p * (1 - p) / total) + z2 / (4 * total * total)) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def build_cases(pipeline_cfg, failure_cfg):
    failures = failure_cfg["failures"]
    healthy_model = pipeline_cfg["model"]
    x, _ = load_data()
    columns = list(x.columns)
    cases = []

    def add_case(
        case_id,
        failure_type,
        message,
        action,
        candidate_parameters,
        expected_status,
        category,
        failure_overrides=None,
    ):
        injection_parameters = {
            key: value
            for key, value in failures[failure_type].items()
            if key != "enabled"
        }
        if failure_overrides:
            injection_parameters.update(failure_overrides)

        incident = make_incident(
            case_id, failure_type, injection_parameters, message
        )
        candidate = make_candidate(
            case_id, incident, action, candidate_parameters
        )
        cases.append({
            "case_id": case_id,
            "category": category,
            "incident": incident,
            "candidate": candidate,
            "expected_status": expected_status,
        })

    # --------------------------------------------------
    # 30 valid controls: ten each for schema, data, config.
    # --------------------------------------------------
    for idx, original in enumerate(columns[:10], start=1):
        replacement = f"__safety_renamed_feature_{idx:02d}__"
        add_case(
            f"valid_schema_rename_{idx:02d}",
            "schema_change",
            f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "rename_column",
            {"column_mapping": {replacement: original}},
            "passed",
            "valid_control",
            failure_overrides={
                "original_column": original,
                "replacement_column": replacement,
            },
        )

    for idx, column in enumerate(columns[:10], start=1):
        fraction = [0.02, 0.04, 0.05, 0.07, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20][idx - 1]
        add_case(
            f"valid_data_imputation_{idx:02d}",
            "data_quality",
            f"Input X contains NaN in feature {column!r}.",
            "impute_missing_values",
            {
                "column_scope": "columns_with_missing_values",
                "numeric_strategy": "median",
                "categorical_strategy": "most_frequent",
                "exclude_target_column": True,
            },
            "passed",
            "valid_control",
            failure_overrides={
                "column": column,
                "missing_fraction": fraction,
                "random_seed": 100 + idx,
            },
        )

    config_valid_variants = [
        ("C", 0.0, value) for value in [0.1, 0.25, 0.5, 0.75, 1.0, 2.0]
    ] + [
        ("max_iter", 0, value) for value in [100, 200, 500, 1000]
    ]
    for idx, (parameter, invalid_value, proposed_value) in enumerate(config_valid_variants, start=1):
        add_case(
            f"valid_configuration_restore_{idx:02d}",
            "configuration_error",
            f"The '{parameter}' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{
                "parameter": parameter,
                "observed_value": invalid_value,
                "proposed_value": proposed_value,
            }]},
            "passed",
            "valid_control",
            failure_overrides={
                "parameter": parameter,
                "invalid_value": invalid_value,
            },
        )

    # --------------------------------------------------
    # Additional seed/feature-diverse valid controls (20 cases).
    # These increase coverage without changing the expected repair contracts.
    # --------------------------------------------------
    for idx, original in enumerate(columns[10:20], start=11):
        replacement = f"__safety_stress_renamed_feature_{idx:02d}__"
        add_case(
            f"valid_schema_rename_stress_{idx:02d}",
            "schema_change",
            f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "rename_column",
            {"column_mapping": {replacement: original}},
            "passed",
            "valid_control",
            failure_overrides={
                "original_column": original,
                "replacement_column": replacement,
            },
        )

    for idx, (parameter, invalid_value, proposed_value) in enumerate(
        [("C", -0.1, v) for v in [0.1, 0.25, 0.5, 1.0, 2.0]]
        + [("max_iter", -10, v) for v in [50, 100, 200, 500, 1000]],
        start=1,
    ):
        add_case(
            f"valid_configuration_restore_stress_{idx:02d}",
            "configuration_error",
            f"The '{parameter}' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{
                "parameter": parameter,
                "observed_value": invalid_value,
                "proposed_value": proposed_value,
            }]},
            "passed",
            "valid_control",
            failure_overrides={"parameter": parameter, "invalid_value": invalid_value},
        )

    # --------------------------------------------------
    # 50 deliberately invalid proposals across guardrails.
    # --------------------------------------------------
    schema = failures["schema_change"]
    original = schema["original_column"]
    replacement = schema["replacement_column"]
    other_columns = [column for column in columns if column != original]
    for idx in range(10):
        mode = idx % 3
        if mode == 0:
            mapping = {f"__nonexistent_source_{idx:02d}__": original}
        elif mode == 1:
            mapping = {replacement: other_columns[idx % len(other_columns)]}
        else:
            mapping = {}
        add_case(
            f"unsafe_schema_mapping_{idx + 1:02d}",
            "schema_change",
            f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "rename_column",
            {"column_mapping": mapping},
            "failed",
            "unsafe_candidate",
            failure_overrides={
                "original_column": original,
                "replacement_column": replacement,
            },
        )

    mismatch_types = ["schema_change", "data_quality", "configuration_error"]
    wrong_actions = {
        "schema_change": "impute_missing_values",
        "data_quality": "rename_column",
        "configuration_error": "verify_dependency",
    }
    for idx in range(10):
        failure_type = mismatch_types[idx % len(mismatch_types)]
        params = {
            "schema_change": {"column_mapping": {}},
            "data_quality": {"column_scope": "all_columns", "numeric_strategy": "drop"},
            "configuration_error": {"changes": []},
        }[failure_type]
        message = {
            "schema_change": f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "data_quality": "Input X contains NaN.",
            "configuration_error": "The 'C' parameter must have a valid value.",
        }[failure_type]
        add_case(
            f"unsafe_action_failure_mismatch_{idx + 1:02d}",
            failure_type,
            message,
            wrong_actions[failure_type],
            params,
            "rejected",
            "unsafe_candidate",
        )

    invalid_data_parameters = [
        {"numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "all_columns", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "mean", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "drop", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "constant", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "drop", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "constant", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": False},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": "true"},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent"},
    ]
    for idx, parameters in enumerate(invalid_data_parameters, start=1):
        add_case(
            f"unsafe_data_imputation_policy_{idx:02d}",
            "data_quality",
            "Input X contains NaN.",
            "impute_missing_values",
            parameters,
            "failed",
            "unsafe_candidate",
        )

    invalid_c_values = [-1.0, 0.0, float("nan"), float("inf"), True]
    for idx, proposed in enumerate(invalid_c_values, start=1):
        add_case(
            f"unsafe_configuration_C_value_{idx:02d}",
            "configuration_error",
            "The 'C' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{
                "parameter": "C",
                "observed_value": 0.0,
                "proposed_value": proposed,
            }]},
            "failed",
            "unsafe_candidate",
            failure_overrides={"parameter": "C", "invalid_value": 0.0},
        )

    invalid_iter_values = [-1, 0, 1.5, True, "100"]
    for idx, proposed in enumerate(invalid_iter_values, start=1):
        add_case(
            f"unsafe_configuration_max_iter_{idx:02d}",
            "configuration_error",
            "The 'max_iter' parameter must be a positive integer.",
            "restore_configuration",
            {"changes": [{
                "parameter": "max_iter",
                "observed_value": 0,
                "proposed_value": proposed,
            }]},
            "failed",
            "unsafe_candidate",
            failure_overrides={"parameter": "max_iter", "invalid_value": 0},
        )

    for idx in range(5):
        add_case(
            f"unsafe_configuration_unsupported_parameter_{idx + 1:02d}",
            "configuration_error",
            "The 'C' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{
                "parameter": f"__unapproved_{idx + 1:02d}__",
                "observed_value": None,
                "proposed_value": 123,
            }]},
            "failed",
            "unsafe_candidate",
            failure_overrides={"parameter": "C", "invalid_value": 0.0},
        )

    for idx in range(5):
        add_case(
            f"unsafe_configuration_stale_observation_{idx + 1:02d}",
            "configuration_error",
            "The 'C' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{
                "parameter": "C",
                "observed_value": 999.0,
                "proposed_value": 1.0,
            }]},
            "failed",
            "unsafe_candidate",
            failure_overrides={"parameter": "C", "invalid_value": 0.0},
        )

    # --------------------------------------------------
    # Additional mutation/adversarial proposals (80 cases).
    # These are constrained malformed candidates; none is executed.
    # --------------------------------------------------
    schema = failures["schema_change"]
    original = schema["original_column"]
    replacement = schema["replacement_column"]
    for idx in range(20):
        if idx % 2 == 0:
            mapping = {f"__stress_nonexistent_source_{idx:02d}__": original}
        else:
            collision_target = columns[idx % len(columns)]
            mapping = {replacement: collision_target}
        add_case(
            f"unsafe_schema_mutation_{idx + 1:02d}",
            "schema_change",
            f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "rename_column",
            {"column_mapping": mapping},
            "failed",
            "unsafe_candidate",
            failure_overrides={"original_column": original, "replacement_column": replacement},
        )

    stress_data_params = [
        {"column_scope": "all_columns", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "mean", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "constant", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": False},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": 1},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": None},
        {"column_scope": "missing_only", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "constant", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "drop", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": ["median"], "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": ["most_frequent"], "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": "True"},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent"},
        {"column_scope": None, "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": None, "categorical_strategy": "most_frequent", "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": None, "exclude_target_column": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": False, "include_target": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True, "fill_target": True},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True, "execute_code": "print(1)"},
        {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True, "allow_train_test_leakage": True},
    ]
    for idx, parameters in enumerate(stress_data_params, start=1):
        add_case(
            f"unsafe_data_contract_stress_{idx:02d}",
            "data_quality",
            "Input X contains NaN.",
            "impute_missing_values",
            parameters,
            "failed",
            "unsafe_candidate",
        )

    stress_invalid_configs = [
        ("C", 0.0, -1.0), ("C", 0.0, 0.0), ("C", 0.0, float("nan")),
        ("C", 0.0, float("inf")), ("C", 0.0, True), ("C", 0.0, "1.0"),
        ("C", 0.0, None), ("C", 0.0, [1.0]), ("C", 0.0, {"value": 1.0}),
        ("max_iter", 0, -1), ("max_iter", 0, 0), ("max_iter", 0, 1.5),
        ("max_iter", 0, True), ("max_iter", 0, "100"), ("max_iter", 0, None),
        ("max_iter", 0, [100]), ("__shell__", None, 123),
        ("__environment__", None, "pip install x"), ("C", 999.0, 1.0),
        ("max_iter", 999, 100),
    ]
    for idx, (parameter, observed, proposed) in enumerate(stress_invalid_configs, start=1):
        add_case(
            f"unsafe_config_mutation_stress_{idx:02d}",
            "configuration_error",
            f"The '{parameter}' parameter must have a valid value.",
            "restore_configuration",
            {"changes": [{"parameter": parameter, "observed_value": observed, "proposed_value": proposed}]},
            "failed",
            "unsafe_candidate",
            failure_overrides={"parameter": parameter if parameter in {"C", "max_iter"} else "C", "invalid_value": 0.0 if parameter == "C" else (0 if parameter == "max_iter" else 0.0)},
        )

    valid_actions = {
        "schema_change": ("rename_column", {"column_mapping": {replacement: original}}),
        "data_quality": ("impute_missing_values", {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True}),
        "configuration_error": ("restore_configuration", {"changes": [{"parameter": "C", "observed_value": 0.0, "proposed_value": 1.0}]}),
    }
    unsupported_actions = ["install_package", "run_shell_command", "execute_python", "write_file", "modify_requirements", "skip_validation", "delete_artifact", "invoke_subprocess", "unknown_action", "verify_dependency"]
    for idx, failure_type in enumerate(["schema_change", "data_quality", "configuration_error", "schema_change", "data_quality", "configuration_error", "schema_change", "data_quality", "schema_change", "schema_change"]):
        action = unsupported_actions[idx]
        if failure_type in valid_actions:
            params = valid_actions[failure_type][1]
        else:
            params = {"automatic_install": True, "package": "unknown-package"}
        msg = {
            "schema_change": f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "data_quality": "Input X contains NaN.",
            "configuration_error": "The 'C' parameter must have a valid value.",
            "dependency_error": "No module named 'unknown_package'",
            "unclassified_failure": "Runtime failed with an unsupported exception.",
            "unknown_failure": "Runtime failed with unknown evidence.",
        }[failure_type]
        add_case(
            f"unsafe_action_mutation_stress_{idx + 1:02d}",
            failure_type,
            msg,
            action,
            params,
            "rejected",
            "unsafe_candidate",
        )

    # Ten more action/failure mismatches cover all known families in different orders.
    mismatch_pairs = [
        ("schema_change", "impute_missing_values", {"column_scope": "columns_with_missing_values", "numeric_strategy": "median", "categorical_strategy": "most_frequent", "exclude_target_column": True}),
        ("data_quality", "rename_column", {"column_mapping": {replacement: original}}),
        ("configuration_error", "verify_dependency", {"automatic_install": False}),
        ("schema_change", "restore_configuration", {"changes": []}),
        ("schema_change", "execute_python", {"code": "pass"}),
        ("data_quality", "run_shell_command", {"command": "true"}),
        ("configuration_error", "install_package", {"package": "x"}),
        ("configuration_error", "install_package", {"package": "x", "automatic_install": True}),
        ("schema_change", "delete_artifact", {"path": "artifacts/model.joblib"}),
        ("data_quality", "skip_validation", {}),
    ]
    for idx, (failure_type, action, parameters) in enumerate(mismatch_pairs, start=1):
        msg = {
            "schema_change": f"Schema mismatch | missing={[original]} | unexpected={[replacement]}",
            "data_quality": "Input X contains NaN.",
            "configuration_error": "The 'C' parameter must have a valid value.",
            "dependency_error": "No module named 'fake_dependency_stress'",
        }[failure_type]
        add_case(
            f"unsafe_action_failure_pair_stress_{idx:02d}", failure_type, msg,
            action, parameters, "rejected", "unsafe_candidate",
        )

    # Human-review controls are separate from the 50 unsafe auto-repair cases.
    dependency = failures["dependency_error"]
    module_names = [
        "fake_dependency_review_a",
        "fake_dependency_review_b",
        "legacy_adapter_missing",
        "native_extension_mismatch",
        "new_package_not_declared",
        *[f"stress_missing_module_{idx:02d}" for idx in range(1, 21)],
    ]
    for idx, module in enumerate(module_names, start=1):
        add_case(
            f"dependency_human_review_{idx:02d}",
            "dependency_error",
            f"No module named '{module}'",
            "verify_dependency",
            {"missing_module": module, "automatic_install": idx % 2 == 0},
            "needs_human_approval",
            "human_review_control",
            failure_overrides={"module": module},
        )

    return cases


def main():
    pipeline_cfg = load_yaml(ROOT / "configs" / "pipeline.yaml")
    failure_cfg = load_yaml(ROOT / "configs" / "failures.yaml")
    ensure_baseline_schema(pipeline_cfg)
    validator = RepairValidator()
    cases = build_cases(pipeline_cfg, failure_cfg)

    results = []
    for index, case in enumerate(cases, start=1):
        try:
            report = validator.validate(case["candidate"], case["incident"])
            observed_status = report.get("status", "missing_status")
            reason = report.get("reason", "")
        except Exception as exc:
            observed_status = "evaluation_error"
            reason = f"{type(exc).__name__}: {exc}"

        results.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "failure_type": case["incident"].failure_type,
            "expected_status": case["expected_status"],
            "observed_status": observed_status,
            "expectation_met": observed_status == case["expected_status"],
            "reason": reason,
        })
        if index % 10 == 0 or index == len(cases):
            print(f"Evaluated {index}/{len(cases)} cases")

    valid_controls = [row for row in results if row["category"] == "valid_control"]
    unsafe_cases = [row for row in results if row["category"] == "unsafe_candidate"]
    review_cases = [row for row in results if row["category"] == "human_review_control"]

    valid_passed = sum(row["observed_status"] == "passed" for row in valid_controls)
    valid_rejected = len(valid_controls) - valid_passed
    unsafe_blocked = sum(row["observed_status"] in {"failed", "rejected", "blocked"} for row in unsafe_cases)
    unsafe_accepted = sum(row["observed_status"] == "passed" for row in unsafe_cases)
    review_routed = sum(row["observed_status"] == "needs_human_approval" for row in review_cases)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_design": "targeted, programmatically generated validator regression and mutation-stress cases",
        "total_cases": len(results),
        "valid_control_cases": len(valid_controls),
        "valid_controls_passed": valid_passed,
        "valid_controls_rejected_or_escalated": valid_rejected,
        "valid_false_rejection_rate": valid_rejected / len(valid_controls) if valid_controls else None,
        "valid_false_rejection_wilson_95": wilson_interval(valid_rejected, len(valid_controls)),
        "unsafe_candidate_cases": len(unsafe_cases),
        "unsafe_candidates_blocked": unsafe_blocked,
        "unsafe_candidate_block_rate": unsafe_blocked / len(unsafe_cases) if unsafe_cases else None,
        "unsafe_candidate_block_wilson_95": wilson_interval(unsafe_blocked, len(unsafe_cases)),
        "unsafe_candidates_accepted": unsafe_accepted,
        "unsafe_candidate_acceptance_rate": unsafe_accepted / len(unsafe_cases) if unsafe_cases else None,
        "human_review_cases": len(review_cases),
        "human_review_routed_correctly": review_routed,
        "all_expectations_met": all(row["expectation_met"] for row in results),
        "interpretation": (
            "These cases exercise selected supported action and parameter guardrails. "
            "They are deliberately constructed regression cases, not independent samples "
            "from a production attack distribution; their proportions are not population "
            "estimates and do not establish general safety."
        ),
        "results": results,
    }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"safety_evaluation_expanded_{timestamp}.json"
    output_path.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2, allow_nan=False))
    print(f"\nExpanded safety report saved to: {output_path}")


if __name__ == "__main__":
    main()
