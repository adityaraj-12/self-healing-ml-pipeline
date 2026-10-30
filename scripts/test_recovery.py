import json

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
CANDIDATE_PATH = "artifacts/incidents/repair_candidates.jsonl"
VALIDATION_PATH = "artifacts/incidents/validation_results.jsonl"
RECOVERY_PATH = "artifacts/incidents/recovery_results.jsonl"


def append_jsonl(path, record):
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def main():
    incidents = IncidentStore(
        INCIDENT_PATH
    ).get_all()

    if not incidents:
        raise RuntimeError(
            "No incidents found. Run a failure experiment first."
        )

    incident = incidents[-1]

    # 1. Generate RCA and a fresh candidate for this incident.
    rca = RuleBasedRCA().analyze(incident)

    candidate_obj = RepairGenerator().generate(
        incident,
        rca
    )

    candidate = candidate_obj.to_dict()

    append_jsonl(CANDIDATE_PATH, candidate)

    print("\nREPAIR CANDIDATE")
    print(json.dumps(candidate, indent=2))

    # 2. Validate this exact candidate.
    validator = RepairValidator()

    validation_report = validator.validate(
        candidate,
        incident
    )

    validator.save_report(
        validation_report,
        VALIDATION_PATH
    )

    print("\nVALIDATION")
    print(json.dumps(validation_report, indent=2))

    if validation_report.get("status") != "passed":
        print(
            "\nRecovery blocked: sandbox validation did not pass."
        )
        return

    # 3. Recover only after validation succeeds.
    engine = RecoveryEngine()

    recovery_result = engine.recover(
        incident,
        candidate,
        validation_report
    )

    engine.save_result(
        recovery_result,
        RECOVERY_PATH
    )

    print("\nRECOVERY RESULT")
    print(json.dumps(recovery_result, indent=2))


if __name__ == "__main__":
    main()