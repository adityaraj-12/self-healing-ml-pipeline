"""Matched policy-gate ablation using the real validator.

The policy arm and no-policy arm receive identical fixed proposals.
Both use RepairValidator.validate() and the side-effect-free recovery
eligibility assessment. RecoveryEngine.recover() is never called.

The validator may simulate repairs inside its temporary workspace and
trains/evaluates a model for data-quality validation. It does not write
recovered pipeline models or metrics through the recovery engine.
"""

import argparse
import json
import os

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from benchmarks.policy_gate_ablation import build_proposals
from healing.repair.repair_policy import enforce_repair_policy
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"

FAILURE_PARAMETERS = {
    "schema_change": {
        "original_column": "mean radius",
        "replacement_column": "mean_radius",
    },
    "data_quality": {
        "column": "mean radius",
        "missing_fraction": 0.10,
        "random_seed": 42,
    },
    "configuration_error": {
        "parameter": "C",
        "invalid_value": 0.0,
    },
    "dependency_error": {
        "module": "fake_ml_dependency",
    },
}

CANDIDATE_PARAMETERS = {
    "schema_change": {
        "column_mapping": {
            "mean_radius": "mean radius",
        },
        "semantic_equivalence_required": True,
    },
    "data_quality": {
        "column_scope": "columns_with_missing_values",
        "numeric_strategy": "median",
        "categorical_strategy": "most_frequent",
        "exclude_target_column": True,
    },
    "configuration_error": {
        "changes": [{
            "parameter": "C",
            "observed_value": 0.0,
            "proposed_value": 1.0,
        }],
    },
    "dependency_error": {
        "module": "fake_ml_dependency",
    },
}


def build_matched_proposals():
    """Attach consistent incident identities and validator-valid controls."""
    proposals = build_proposals()
    cases = []

    for index, proposal in enumerate(proposals, 1):
        failure_type = proposal["failure_type"]
        incident_id = f"INC-POLICY-V2-{index:03d}"
        candidate_id = f"RC-POLICY-V2-{index:03d}"

        parameters = deepcopy(
            CANDIDATE_PARAMETERS.get(failure_type, {})
        )

        # Preserve the V1 module identity for its forged-approval proposals.
        if proposal["expected_category"] == "approval_bypass_attempt":
            parameters = deepcopy(proposal.get("parameters", parameters))

        incident_parameters = deepcopy(
            FAILURE_PARAMETERS.get(failure_type, {})
        )

        incident = {
            "incident_id": incident_id,
            "failure_type": failure_type,
            "context": {
                "failure_injection": {
                    "parameters": incident_parameters,
                },
            },
        }

        candidate = {
            "candidate_id": candidate_id,
            "incident_id": incident_id,
            "failure_type": failure_type,
            "action": proposal["action"],
            "parameters": parameters,
            "requires_human_approval": bool(
                proposal.get("requires_human_approval", False)
            ),
        }

        cases.append({
            "case_id": proposal["case_id"],
            "expected_category": proposal["expected_category"],
            "incident": incident,
            "candidate": candidate,
        })

    return cases


def _incident_object(data):
    return SimpleNamespace(
        incident_id=data["incident_id"],
        failure_type=data["failure_type"],
        context=deepcopy(data["context"]),
    )


def evaluate_arm(case, arm, validator, assessor):
    """Run one proposal through either the policy or no-policy arm."""
    raw_candidate = deepcopy(case["candidate"])
    candidate = deepcopy(raw_candidate)
    incident = _incident_object(case["incident"])

    input_approval = candidate["requires_human_approval"]
    policy_seconds = 0.0
    policy_error = None

    if arm == "policy_gated":
        started = perf_counter()
        try:
            candidate = enforce_repair_policy(candidate)
            policy_decision = "allowed"
        except ValueError as exc:
            policy_decision = "rejected"
            policy_error = str(exc)
        policy_seconds = perf_counter() - started
    elif arm == "no_policy":
        policy_decision = "bypassed"
    else:
        raise ValueError(f"Unknown experiment arm: {arm}")

    approval_overridden = (
        candidate.get("requires_human_approval") is True
        and input_approval is False
    )

    if policy_decision == "rejected":
        return {
            "arm": arm,
            "policy_decision": policy_decision,
            "policy_error": policy_error,
            "policy_seconds": round(policy_seconds, 8),
            "validator_invoked": False,
            "validator_status": "not_invoked",
            "validator_reason": None,
            "validator_checks": 0,
            "failed_validator_checks": [],
            "recovery_eligibility_assessed": False,
            "recovery_eligibility_status": "not_assessed",
            "recovery_eligibility_reason": None,
            "approval_flag_input": input_approval,
            "approval_flag_after_policy": candidate.get(
                "requires_human_approval"
            ),
            "approval_flag_overridden": approval_overridden,
            "final_decision": "blocked",
            "validator_seconds": 0.0,
        }

    validation_error = None
    validation_started = perf_counter()

    try:
        report = validator.validate(
            deepcopy(candidate),
            incident,
        )
    except Exception as exc:
        validation_error = f"{type(exc).__name__}: {exc}"
        report = {
            "candidate_id": candidate["candidate_id"],
            "incident_id": incident.incident_id,
            "failure_type": candidate["failure_type"],
            "status": "failed",
            "reason": validation_error,
            "checks": [],
        }

    validator_seconds = perf_counter() - validation_started
    checks = report.get("checks") or []
    failed_checks = [
        item.get("check", "unnamed_check")
        for item in checks
        if isinstance(item, dict) and not item.get("passed", False)
    ]

    eligibility = assessor.assess_recovery_eligibility(
        incident,
        candidate,
        report,
    )

    return {
        "arm": arm,
        "policy_decision": policy_decision,
        "policy_error": policy_error,
        "policy_seconds": round(policy_seconds, 8),
        "validator_invoked": True,
        "validator_status": report.get("status", "missing_status"),
        "validator_reason": report.get("reason"),
        "validator_error": validation_error,
        "validator_checks": len(checks),
        "failed_validator_checks": failed_checks,
        "recovery_eligibility_assessed": True,
        "recovery_eligibility_status": eligibility["status"],
        "recovery_eligibility_reason": eligibility["reason"],
        "approval_flag_input": input_approval,
        "approval_flag_after_policy": candidate.get(
            "requires_human_approval"
        ),
        "approval_flag_overridden": approval_overridden,
        "final_decision": eligibility["status"],
        "validator_seconds": round(validator_seconds, 8),
    }


def _arm_summary(rows):
    return {
        "cases": len(rows),
        "policy_rejections": sum(
            row["policy_decision"] == "rejected" for row in rows
        ),
        "validator_invocations": sum(
            row["validator_invoked"] for row in rows
        ),
        "validator_status_counts": dict(sorted(Counter(
            row["validator_status"]
            for row in rows
            if row["validator_invoked"]
        ).items())),
        "final_decision_counts": dict(sorted(Counter(
            row["final_decision"] for row in rows
        ).items())),
        "dependency_approval_flags_overridden": sum(
            row["approval_flag_overridden"] for row in rows
        ),
        "recovery_eligibility_assessments": sum(
            row["recovery_eligibility_assessed"] for row in rows
        ),
        "mean_validator_seconds": (
            round(
                sum(row["validator_seconds"] for row in rows)
                / sum(row["validator_invoked"] for row in rows),
                6,
            )
            if any(row["validator_invoked"] for row in rows)
            else None
        ),
    }


def evaluate_matched_proposals(case_ids=None, validator=None):
    cases = build_matched_proposals()

    if case_ids is not None:
        wanted = set(case_ids)
        known = {case["case_id"] for case in cases}
        unknown = sorted(wanted - known)
        if unknown:
            raise ValueError("Unknown case IDs: " + ", ".join(unknown))
        cases = [case for case in cases if case["case_id"] in wanted]

    if not cases:
        raise ValueError("No policy-gate cases selected.")

    validator = validator or RepairValidator()

    # This method only assesses eligibility. It never calls recover().
    assessor = RecoveryEngine.__new__(RecoveryEngine)

    paired_rows = []

    for case in cases:
        gated = evaluate_arm(
            case, "policy_gated", validator, assessor
        )
        bypass = evaluate_arm(
            case, "no_policy", validator, assessor
        )

        paired_rows.append({
            "case_id": case["case_id"],
            "expected_category": case["expected_category"],
            "failure_type": case["candidate"]["failure_type"],
            "action": case["candidate"]["action"],
            "candidate_id": case["candidate"]["candidate_id"],
            "candidate_parameters": case["candidate"]["parameters"],
            "input_requires_human_approval": (
                case["candidate"]["requires_human_approval"]
            ),
            "incident_injection_parameters": (
                case["incident"]["context"]["failure_injection"]["parameters"]
            ),
            "policy_gated": gated,
            "no_policy": bypass,
            "terminal_decisions_agree": (
                gated["final_decision"] == bypass["final_decision"]
            ),
        })

    gated_rows = [row["policy_gated"] for row in paired_rows]
    bypass_rows = [row["no_policy"] for row in paired_rows]

    discordances = [
        {
            "case_id": row["case_id"],
            "policy_gated": row["policy_gated"]["final_decision"],
            "no_policy": row["no_policy"]["final_decision"],
        }
        for row in paired_rows
        if not row["terminal_decisions_agree"]
    ]

    invalid_dependency_actions = [
        row for row in paired_rows
        if row["failure_type"] == "dependency_error"
        and row["expected_category"] in {
            "action_failure_mismatch",
            "unsupported_action",
        }
    ]

    summary = {
        "cases": len(paired_rows),
        "policy_gated_arm": _arm_summary(gated_rows),
        "no_policy_arm": _arm_summary(bypass_rows),
        "paired_terminal_outcome_agreement": (
            len(paired_rows) - len(discordances)
        ),
        "paired_terminal_outcome_discordances": len(discordances),
        "discordant_cases": discordances,
        "invalid_dependency_actions_routed_to_review_without_policy": sum(
            row["no_policy"]["final_decision"] == "needs_human_approval"
            for row in invalid_dependency_actions
        ),
        "invalid_dependency_actions_rejected_by_policy": sum(
            row["policy_gated"]["final_decision"] == "blocked"
            and row["policy_gated"]["policy_decision"] == "rejected"
            for row in invalid_dependency_actions
        ),
        "recovery_execution_calls": 0,
        "persistent_recovery_artifacts_written_by_runner": 0,
    }

    return paired_rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-ids",
        nargs="+",
        default=None,
        help="Optional exact proposal IDs for a real-validator smoke test.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    args = parser.parse_args()

    os.chdir(ROOT)

    try:
        rows, summary = evaluate_matched_proposals(args.case_ids)
    except ValueError as exc:
        parser.error(str(exc))

    output = {
        "schema": "policy-gate-matched-ablation-v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation": (
            "Matched fixed-proposal comparison of the action policy gate "
            "with and without the gate, using the real validator and "
            "side-effect-free recovery eligibility assessment."
        ),
        "proposal_source": (
            "The 36 fixed, handcrafted proposal records from policy-gate V1; "
            "candidate and incident identities and valid control parameters "
            "are explicitly bound for both arms."
        ),
        "safety_boundary": (
            "RecoveryEngine.recover() is never called. The real validator "
            "may apply controlled repairs inside its temporary workspace "
            "and trains/evaluates a model for data-quality validation. "
            "The experiment does not create recovered pipeline models or "
            "metrics, execute arbitrary code, install packages, or make "
            "LLM/provider requests."
        ),
        "interpretation_limit": (
            "This is a matched decision-level ablation on handcrafted "
            "proposals, not a live LLM-generation experiment or a measure "
            "of end-to-end recovery success or general security."
        ),
        **summary,
        "results": rows,
    }

    output_path = (
        args.output
        if args.output is not None
        else RESULT_DIR / (
            "policy_gate_ablation_v2_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
    )

    if not output_path.is_absolute():
        output_path = ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "output": str(output_path),
        "cases": summary["cases"],
        "policy_gated_arm": summary["policy_gated_arm"],
        "no_policy_arm": summary["no_policy_arm"],
        "paired_terminal_outcome_agreement": (
            summary["paired_terminal_outcome_agreement"]
        ),
        "paired_terminal_outcome_discordances": (
            summary["paired_terminal_outcome_discordances"]
        ),
        "invalid_dependency_actions_routed_to_review_without_policy": (
            summary[
                "invalid_dependency_actions_routed_to_review_without_policy"
            ]
        ),
        "invalid_dependency_actions_rejected_by_policy": (
            summary["invalid_dependency_actions_rejected_by_policy"]
        ),
        "recovery_execution_calls": summary["recovery_execution_calls"],
    }, indent=2))


if __name__ == "__main__":
    main()
