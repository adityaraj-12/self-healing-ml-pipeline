from types import SimpleNamespace

import pytest

from healing.recovery.recovery_engine import RecoveryEngine


def make_inputs():
    incident = SimpleNamespace(
        incident_id="INC-POLICY-TEST",
        failure_type="data_quality",
    )

    candidate = {
        "candidate_id": "RC-POLICY-TEST",
        "incident_id": incident.incident_id,
        "failure_type": incident.failure_type,
        "requires_human_approval": False,
    }

    report = {
        "candidate_id": candidate["candidate_id"],
        "incident_id": incident.incident_id,
        "failure_type": incident.failure_type,
        "status": "passed",
    }

    # The method under test must not need initialized recovery components.
    engine = RecoveryEngine.__new__(RecoveryEngine)
    return engine, incident, candidate, report


def test_matching_validated_candidate_is_eligible_without_recovery_side_effects():
    engine, incident, candidate, report = make_inputs()

    decision = engine.assess_recovery_eligibility(
        incident, candidate, report
    )

    assert decision["eligible"] is True
    assert decision["status"] == "eligible"


@pytest.mark.parametrize(
    "mutation, expected_status",
    [
        ("candidate_incident_id", "blocked"),
        ("candidate_failure_type", "blocked"),
        ("report_candidate_id", "blocked"),
        ("report_incident_id", "blocked"),
        ("report_failure_type", "blocked"),
        ("candidate_approval", "needs_human_approval"),
        ("dependency_false_approval", "needs_human_approval"),
        ("validator_review", "needs_human_approval"),
        ("validator_failed", "blocked"),
    ],
)
def test_recovery_eligibility_preserves_existing_safety_decisions(
    mutation, expected_status
):
    engine, incident, candidate, report = make_inputs()

    if mutation == "candidate_incident_id":
        candidate["incident_id"] = "INC-OTHER"
    elif mutation == "candidate_failure_type":
        candidate["failure_type"] = "schema_change"
        report["failure_type"] = "schema_change"
    elif mutation == "report_candidate_id":
        report["candidate_id"] = "RC-OTHER"
    elif mutation == "report_incident_id":
        report["incident_id"] = "INC-OTHER"
    elif mutation == "report_failure_type":
        report["failure_type"] = "schema_change"
    elif mutation == "candidate_approval":
        candidate["requires_human_approval"] = True
    elif mutation == "dependency_false_approval":
        incident.failure_type = "dependency_error"
        candidate["failure_type"] = "dependency_error"
        candidate["requires_human_approval"] = False
        report["failure_type"] = "dependency_error"
    elif mutation == "validator_review":
        report["status"] = "needs_human_approval"
    elif mutation == "validator_failed":
        report["status"] = "failed"

    decision = engine.assess_recovery_eligibility(
        incident, candidate, report
    )

    assert decision["eligible"] is False
    assert decision["status"] == expected_status
