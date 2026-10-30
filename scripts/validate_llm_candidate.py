
import argparse
import json
from pathlib import Path

from healing.incidents.incident_store import IncidentStore
from healing.validation.repair_validator import RepairValidator


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
CANDIDATE_PATH = (
    "artifacts/incidents/llm_repair_candidates.jsonl"
)
REPORT_PATH = (
    "artifacts/incidents/validation_results.jsonl"
)


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"File does not exist: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--failure-type",
        required=True,
        choices=[
            "schema_change",
            "data_quality",
            "configuration_error",
            "dependency_error",
        ],
    )

    args = parser.parse_args()

    # Load candidates and select the latest one for this type.
    candidates = read_jsonl(CANDIDATE_PATH)

    matching = [
        candidate
        for candidate in candidates
        if candidate.get("failure_type")
        == args.failure_type
    ]

    if not matching:
        raise RuntimeError(
            f"No LLM candidate found for {args.failure_type}. "
            "Generate a candidate first."
        )

    candidate = matching[-1]

    # Match by exact incident ID, not by list position.
    incidents = IncidentStore(
        INCIDENT_PATH
    ).get_all()

    incident_map = {
        incident.incident_id: incident
        for incident in incidents
    }

    incident = incident_map.get(
        candidate["incident_id"]
    )

    if incident is None:
        raise RuntimeError(
            "The candidate references an incident "
            "that cannot be found."
        )

    if incident.failure_type != candidate["failure_type"]:
        raise RuntimeError(
            "Candidate and incident failure types do not match."
        )

    print("\nSelected candidate:")
    print(candidate["candidate_id"])

    print("Matched incident:")
    print(incident.incident_id)

    validator = RepairValidator()

    report = validator.validate(
        candidate,
        incident
    )

    validator.save_report(
        report,
        REPORT_PATH
    )

    print("\nValidation report:")
    print(json.dumps(report, indent=2))

    print("\nValidation status:", report["status"])

    if report["status"] == "passed":
        print(
            "Sandbox checks passed. Recovery is still subject "
            "to the approval policy."
        )
    else:
        print(
            "The candidate has not passed validation and "
            "must not be applied automatically."
        )


if __name__ == "__main__":
    main()
