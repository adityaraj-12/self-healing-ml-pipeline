"""Run a small, separately authored challenge set for rule-based RCA.

The challenge cases are intentionally not loaded from trial_cases.yaml. They
probe variants that differ from the original injected scenarios. This is a
small diagnostic exercise, not a representative estimate of production RCA
accuracy.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"

CHALLENGE_CASES = [
    {
        "case_id": "schema_multi_column_mismatch",
        "failure_type": "schema_change",
        "error_message": (
            "Schema mismatch | missing=['mean radius', 'mean texture'] "
            "| unexpected=['radius_mean', 'texture_mean']"
        ),
        "expected_root_cause_code": "schema_mismatch",
        "reason": "Multiple columns changed; this is not a one-to-one rename.",
    },
    {
        "case_id": "schema_order_or_width_mismatch",
        "failure_type": "schema_change",
        "error_message": (
            "Feature schema does not match the training contract: "
            "expected 30 columns in fixed order, received 29."
        ),
        "expected_root_cause_code": "schema_mismatch",
        "reason": "Different error wording without the original missing/unexpected list format.",
    },
    {
        "case_id": "data_missing_values_new_message",
        "failure_type": "data_quality",
        "error_message": "Input matrix contains NaN values in numeric features.",
        "expected_root_cause_code": "missing_feature_values",
        "reason": "Missing values expressed with a different message template.",
    },
    {
        "case_id": "data_infinite_values",
        "failure_type": "data_quality",
        "error_message": "Input matrix contains positive infinity values.",
        "expected_root_cause_code": "invalid_feature_values",
        "reason": "Non-finite values are distinct from missing values.",
    },
    {
        "case_id": "data_type_mismatch",
        "failure_type": "data_quality",
        "error_message": "Feature 'mean radius' contains string values where numeric values are required.",
        "expected_root_cause_code": "invalid_feature_types",
        "reason": "Feature type incompatibility rather than missingness.",
    },
    {
        "case_id": "config_max_iter_variant",
        "failure_type": "configuration_error",
        "error_message": "The 'max_iter' parameter must be a positive integer.",
        "expected_root_cause_code": "invalid_parameter:max_iter",
        "reason": "A different model parameter from the original C-only trial variants.",
    },
    {
        "case_id": "config_solver_variant",
        "failure_type": "configuration_error",
        "error_message": "The 'solver' parameter is not supported by the selected estimator.",
        "expected_root_cause_code": "invalid_parameter:solver",
        "reason": "A parameter not used in the original controlled scenarios.",
    },
    {
        "case_id": "dependency_new_module_name",
        "failure_type": "dependency_error",
        "error_message": "No module named 'third_party_adapter_v2'.",
        "expected_root_cause_code": "missing_module:third_party_adapter_v2",
        "reason": "An unseen module name rather than one of the three configured fake modules.",
    },
    {
        "case_id": "dependency_binary_compatibility",
        "failure_type": "dependency_error",
        "error_message": "ImportError: incompatible binary ABI between a compiled extension and NumPy.",
        "expected_root_cause_code": "missing_runtime_dependency",
        "reason": "Import incompatibility without a 'No module named ...' message.",
    },
    {
        "case_id": "unknown_permission_error",
        "failure_type": "unknown_runtime_failure",
        "error_message": "PermissionError: access to the model artifact directory was denied.",
        "expected_root_cause_code": "unknown",
        "reason": "Unknown runtime fault should remain unknown rather than be forced into a known class.",
    },
    {
        "case_id": "unknown_resource_timeout",
        "failure_type": "unknown_runtime_failure",
        "error_message": "TimeoutError: pipeline stage exceeded its configured time budget.",
        "expected_root_cause_code": "unknown",
        "reason": "Unknown runtime fault should remain unknown rather than be forced into a known class.",
    },
]


def run_challenge():
    rca = RuleBasedRCA()
    rows = []

    for case in CHALLENGE_CASES:
        incident = SimpleNamespace(
            incident_id=f"RCA-CHALLENGE-{case['case_id']}",
            failure_type=case["failure_type"],
            error_message=case["error_message"],
        )
        result = rca.analyze(incident)
        predicted = result.root_cause_code
        expected = case["expected_root_cause_code"]
        rows.append({
            **case,
            "predicted_root_cause_code": predicted,
            "correct": predicted == expected,
            "rca_method": result.method,
        })

    correct = sum(row["correct"] for row in rows)
    total = len(rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": "separately authored RCA challenge set",
        "case_source": "benchmarks/diagnosis_challenge.py; not trial_cases.yaml",
        "total_cases": total,
        "correct": correct,
        "incorrect": total - correct,
        "accuracy": correct / total if total else None,
        "interpretation": (
            "Small, manually specified challenge set. It is useful for finding "
            "specific rule gaps but is not a representative estimate of "
            "accuracy on production incidents."
        ),
        "results": rows,
    }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"diagnosis_challenge_{timestamp}.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nRCA challenge report saved to: {output_path}")
    return summary


if __name__ == "__main__":
    run_challenge()
