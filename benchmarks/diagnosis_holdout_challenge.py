"""Run a second manually specified RCA challenge outside trial_cases.yaml.

This is a small synthetic challenge intended to exercise message variants and
unknown-failure abstention. It is not an estimate of production accuracy.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"

CASES = [
    ("schema_single_alias_b", "schema_change", "Schema mismatch | missing=['worst area'] | unexpected=['area_worst']", "schema_rename:area_worst->worst area"),
    ("schema_multi_alias_b", "schema_change", "Schema mismatch | missing=['mean radius', 'mean texture'] | unexpected=['rad', 'tex']", "schema_mismatch"),
    ("missing_null_variant", "data_quality", "Null values discovered after feature extraction.", "missing_feature_values"),
    ("missing_na_variant", "data_quality", "Feature block contains <NA> entries.", "missing_feature_values"),
    ("nonfinite_wording_variant", "data_quality", "A non-finite measurement was found during validation.", "invalid_feature_values"),
    ("inf_token_variant", "data_quality", "Preprocessing received +Inf in the numeric feature block.", "invalid_feature_values"),
    ("type_dtype_variant", "data_quality", "dtype object observed for a feature configured as float.", "invalid_feature_types"),
    ("type_numeric_variant", "data_quality", "A string token was supplied where a numeric value is expected.", "invalid_feature_types"),
    ("unclassified_sentinel_variant", "data_quality", "The dataset contains sentinel code -9999 outside the documented domain.", "unclassified_data_quality"),
    ("config_tol_variant", "configuration_error", "The 'tol' parameter must be positive.", "invalid_parameter:tol"),
    ("config_unstructured_message", "configuration_error", "Estimator option 'solver' failed validation without a parameter detail.", "invalid_model_configuration"),
    ("dependency_package_path", "dependency_error", "No module named 'my_vendor.model_bridge_v2'.", "missing_module:my_vendor.model_bridge_v2"),
    ("dependency_native_import", "dependency_error", "ImportError: DLL load failed because a native extension could not be loaded.", "missing_runtime_dependency"),
    ("unknown_permissions_variant", "unknown_runtime_failure", "OSError: permission denied while reading the model artifact metadata.", "unknown"),
    ("unknown_child_process_variant", "unknown_runtime_failure", "RuntimeError: child process exited with signal 9 before returning a result.", "unknown"),
]


def main():
    rca = RuleBasedRCA()
    rows = []
    for case_id, failure_type, message, expected in CASES:
        incident = SimpleNamespace(
            incident_id=f"RCA-HOLDOUT-{case_id}",
            failure_type=failure_type,
            error_message=message,
        )
        result = rca.analyze(incident)
        rows.append({
            "case_id": case_id,
            "failure_type": failure_type,
            "error_message": message,
            "expected_root_cause_code": expected,
            "predicted_root_cause_code": result.root_cause_code,
            "correct": result.root_cause_code == expected,
            "confidence": result.confidence,
        })

    correct = sum(row["correct"] for row in rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": "manually specified synthetic RCA challenge outside trial_cases.yaml",
        "total_cases": len(rows),
        "correct": correct,
        "incorrect": len(rows) - correct,
        "accuracy": correct / len(rows) if rows else None,
        "interpretation": (
            "This small hand-authored challenge probes selected message variants and unknown-fault handling. "
            "It is not a blind evaluation and must not be interpreted as a production accuracy estimate."
        ),
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"diagnosis_holdout_challenge_{timestamp}.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    print(f"\nChallenge report saved to: {output_path}")


if __name__ == "__main__":
    main()
