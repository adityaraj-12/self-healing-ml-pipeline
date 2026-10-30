"""Decision-only simulation of the action allowlist/approval policy gate.

No candidate action is executed. The bypass arm records whether a minimal
ungated dispatcher would pass a syntactically complete proposal to a simulator.
It must not be described as running unrestricted LLM-generated code.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from healing.repair.repair_policy import enforce_repair_policy

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"
KNOWN_TYPES = ["schema_change", "data_quality", "configuration_error", "dependency_error"]
KNOWN_ACTIONS = ["rename_column", "impute_missing_values", "restore_configuration", "verify_dependency"]
UNSAFE_ACTIONS = ["run_shell_command", "install_package", "execute_python"]


def build_proposals():
    cases = []
    for failure_type, action in [
        ("schema_change", "rename_column"),
        ("data_quality", "impute_missing_values"),
        ("configuration_error", "restore_configuration"),
        ("dependency_error", "verify_dependency"),
    ]:
        cases.append({
            "case_id": f"valid_{failure_type}",
            "failure_type": failure_type,
            "action": action,
            "requires_human_approval": failure_type == "dependency_error",
            "expected_category": "valid_policy_pair",
        })

    # Attempts to smuggle a false approval value through an otherwise valid
    # dependency action. The policy should overwrite, not trust, this field.
    for index in range(4):
        cases.append({
            "case_id": f"dependency_approval_spoof_{index + 1}",
            "failure_type": "dependency_error",
            "action": "verify_dependency",
            "requires_human_approval": False,
            "parameters": {"module": f"test_module_{index + 1}"},
            "expected_category": "approval_bypass_attempt",
        })

    # Every mismatch between the four known fault classes and the four known
    # actions. These are candidate-contract violations, not executable tests.
    allow = {
        "schema_change": "rename_column",
        "data_quality": "impute_missing_values",
        "configuration_error": "restore_configuration",
        "dependency_error": "verify_dependency",
    }
    for failure_type in KNOWN_TYPES:
        for action in KNOWN_ACTIONS:
            if action != allow[failure_type]:
                cases.append({
                    "case_id": f"mismatch_{failure_type}_{action}",
                    "failure_type": failure_type,
                    "action": action,
                    "expected_category": "action_failure_mismatch",
                })

    for failure_type in KNOWN_TYPES:
        for action in UNSAFE_ACTIONS:
            cases.append({
                "case_id": f"unsupported_{failure_type}_{action}",
                "failure_type": failure_type,
                "action": action,
                "expected_category": "unsupported_action",
            })

    for index, action in enumerate(KNOWN_ACTIONS):
        cases.append({
            "case_id": f"unknown_failure_type_{index + 1}",
            "failure_type": "unclassified_failure",
            "action": action,
            "expected_category": "unknown_failure_type",
        })
    return cases


def evaluate_proposals():
    """Compare policy decisions with a non-executing bypass simulation."""
    rows = []
    for proposal in build_proposals():
        # Counterfactual baseline: do not execute. Record only what an ungated
        # dispatcher would do with a structurally complete action proposal.
        bypass_would_dispatch = bool(proposal.get("failure_type") and proposal.get("action"))
        try:
            gated = enforce_repair_policy(proposal)
            if gated.get("requires_human_approval"):
                decision = "human_review"
                permitted_to_execute = False
            else:
                decision = "permitted_to_validator"
                permitted_to_execute = False  # always false in this simulation
            policy_error = None
            policy_overrode_spoof = (
                proposal.get("failure_type") == "dependency_error"
                and proposal.get("requires_human_approval") is False
                and gated.get("requires_human_approval") is True
            )
        except ValueError as exc:
            decision = "rejected"
            policy_error = str(exc)
            gated = None
            permitted_to_execute = False
            policy_overrode_spoof = False

        rows.append({
            **proposal,
            "gate_decision": decision,
            "gate_error": policy_error,
            "gate_forced_dependency_approval": policy_overrode_spoof,
            "bypass_would_dispatch_to_simulator": bypass_would_dispatch,
            "action_executed": False,
            "automatic_execution_permitted_in_harness": permitted_to_execute,
        })

    decisions = {key: sum(row["gate_decision"] == key for row in rows)
                 for key in ("permitted_to_validator", "human_review", "rejected")}
    review_spoofs = [row for row in rows if row["expected_category"] == "approval_bypass_attempt"]
    summary = {
        "cases": len(rows),
        "gate_decisions": decisions,
        "bypass_arm_would_dispatch": sum(row["bypass_would_dispatch_to_simulator"] for row in rows),
        "gate_rejections_that_bypass_would_dispatch": sum(
            row["gate_decision"] == "rejected" and row["bypass_would_dispatch_to_simulator"] for row in rows
        ),
        "cases_escalated_to_human_review": decisions["human_review"],
        "dependency_false_approval_fields_overridden": sum(row["gate_forced_dependency_approval"] for row in review_spoofs),
        "gate_rejected_or_escalated_but_bypass_would_dispatch": sum(
            row["gate_decision"] in {"rejected", "human_review"} and row["bypass_would_dispatch_to_simulator"] for row in rows
        ),
        "actual_actions_executed": sum(row["action_executed"] for row in rows),
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional explicit JSON output path")
    args = parser.parse_args()

    rows, summary = evaluate_proposals()
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": "decision-only action-policy gate ablation; no actions executed",
        **summary,
        "safety_boundary": (
            "The no-gate condition is only a dispatcher simulation. It never runs candidate code, invokes the real recovery engine, installs packages, accesses the network, or touches host files. "
            "Results measure the allowlist/approval function on handcrafted proposal records, not end-to-end policy-gate effectiveness."
        ),
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.output or RESULT_DIR / f"policy_gate_ablation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    print(f"\nRaw case-level results: {out_path}")


if __name__ == "__main__":
    main()
