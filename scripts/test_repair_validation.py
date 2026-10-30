import json

from healing.incidents.incident_store import IncidentStore
from healing.repair.repair_generator import RepairGenerator
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.validation.repair_validator import RepairValidator


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
REPORT_PATH = "artifacts/incidents/validation_results.jsonl"
CANDIDATE_PATH = "artifacts/incidents/repair_candidates.jsonl"


def read_jsonl(path):
    results = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
    except FileNotFoundError:
        pass

    return results


def main():
    incident_store = IncidentStore(INCIDENT_PATH)
    incidents = incident_store.get_all()

    if not incidents:
        raise RuntimeError(
            "No incidents found. Run a failure experiment first."
        )

    # Use the newest incident and generate a fresh candidate.
    incident = incidents[-1]

    rca = RuleBasedRCA().analyze(incident)
    candidate_obj = RepairGenerator().generate(incident, rca)
    candidate = candidate_obj.to_dict()

    print("\nREPAIR CANDIDATE")
    print(json.dumps(candidate, indent=2))

    validator = RepairValidator()

    report = validator.validate(
        candidate,
        incident
    )

    validator.save_report(
        report,
        REPORT_PATH
    )

    print("\nVALIDATION REPORT")
    print(json.dumps(report, indent=2))

    print("\nStatus:", report["status"])

    if report["status"] != "passed":
        print(
            "The repair has NOT been approved for application."
        )


if __name__ == "__main__":
    main()