from benchmarks.policy_gate_ablation_v2 import (
    build_matched_proposals,
    evaluate_arm,
    evaluate_matched_proposals,
)
from healing.recovery.recovery_engine import RecoveryEngine


class ContractValidator:
    """Fast test double matching the current validator decision ordering."""

    def __init__(self):
        self.calls = []

    def validate(self, candidate, incident):
        self.calls.append(candidate.copy())

        if candidate["failure_type"] == "dependency_error":
            status = "needs_human_approval"
        else:
            expected = {
                "schema_change": "rename_column",
                "data_quality": "impute_missing_values",
                "configuration_error": "restore_configuration",
            }.get(candidate["failure_type"])

            status = (
                "passed"
                if expected == candidate["action"]
                else "rejected"
            )

        return {
            "candidate_id": candidate["candidate_id"],
            "incident_id": incident.incident_id,
            "failure_type": candidate["failure_type"],
            "status": status,
            "reason": "test validator outcome",
            "checks": [],
        }


def test_v2_builds_36_identity_bound_matched_proposals():
    cases = build_matched_proposals()

    assert len(cases) == 36
    assert len({case["case_id"] for case in cases}) == 36
    assert len({
        case["candidate"]["candidate_id"] for case in cases
    }) == 36

    for case in cases:
        assert (
            case["candidate"]["incident_id"]
            == case["incident"]["incident_id"]
        )
        assert (
            case["candidate"]["failure_type"]
            == case["incident"]["failure_type"]
        )

    schema = next(
        case for case in cases
        if case["case_id"] == "valid_schema_change"
    )
    assert schema["candidate"]["parameters"]["column_mapping"] == {
        "mean_radius": "mean radius"
    }

    quality = next(
        case for case in cases
        if case["case_id"] == "valid_data_quality"
    )
    assert quality["candidate"]["parameters"]["numeric_strategy"] == "median"

    config = next(
        case for case in cases
        if case["case_id"] == "valid_configuration_error"
    )
    assert config["candidate"]["parameters"]["changes"][0] == {
        "parameter": "C",
        "observed_value": 0.0,
        "proposed_value": 1.0,
    }


def test_policy_gate_rejects_invalid_dependency_action_before_validator():
    cases = build_matched_proposals()
    case = next(
        case for case in cases
        if case["case_id"] == (
            "unsupported_dependency_error_install_package"
        )
    )

    gated_validator = ContractValidator()
    bypass_validator = ContractValidator()
    assessor = RecoveryEngine.__new__(RecoveryEngine)

    gated = evaluate_arm(
        case, "policy_gated", gated_validator, assessor
    )
    bypass = evaluate_arm(
        case, "no_policy", bypass_validator, assessor
    )

    assert gated["policy_decision"] == "rejected"
    assert gated["validator_invoked"] is False
    assert gated["final_decision"] == "blocked"
    assert gated_validator.calls == []

    assert bypass["validator_invoked"] is True
    assert bypass["validator_status"] == "needs_human_approval"
    assert bypass["final_decision"] == "needs_human_approval"
    assert len(bypass_validator.calls) == 1


def test_policy_overwrites_forged_dependency_approval_flag():
    cases = build_matched_proposals()
    case = next(
        case for case in cases
        if case["case_id"] == "dependency_approval_spoof_1"
    )

    gated_validator = ContractValidator()
    bypass_validator = ContractValidator()
    assessor = RecoveryEngine.__new__(RecoveryEngine)

    gated = evaluate_arm(
        case, "policy_gated", gated_validator, assessor
    )
    bypass = evaluate_arm(
        case, "no_policy", bypass_validator, assessor
    )

    assert gated["approval_flag_input"] is False
    assert gated["approval_flag_after_policy"] is True
    assert gated["approval_flag_overridden"] is True

    assert bypass["approval_flag_input"] is False
    assert bypass["approval_flag_after_policy"] is False
    assert bypass["approval_flag_overridden"] is False

    assert gated["final_decision"] == "needs_human_approval"
    assert bypass["final_decision"] == "needs_human_approval"


def test_matched_contract_validator_summary_is_paired_and_non_executing():
    validator = ContractValidator()
    rows, summary = evaluate_matched_proposals(validator=validator)

    assert len(rows) == 36
    assert summary["policy_gated_arm"]["policy_rejections"] == 28
    assert summary["policy_gated_arm"]["validator_invocations"] == 8
    assert summary["no_policy_arm"]["validator_invocations"] == 36

    assert summary["policy_gated_arm"]["final_decision_counts"] == {
        "blocked": 28,
        "eligible": 3,
        "needs_human_approval": 5,
    }
    assert summary["no_policy_arm"]["final_decision_counts"] == {
        "blocked": 22,
        "eligible": 3,
        "needs_human_approval": 11,
    }

    assert summary[
        "invalid_dependency_actions_routed_to_review_without_policy"
    ] == 6
    assert summary["invalid_dependency_actions_rejected_by_policy"] == 6
    assert summary["paired_terminal_outcome_discordances"] == 6
    assert summary["recovery_execution_calls"] == 0

    assert all(
        row["policy_gated"]["final_decision"] ==
        row["no_policy"]["final_decision"]
        for row in rows
        if row["failure_type"] != "dependency_error"
    )
