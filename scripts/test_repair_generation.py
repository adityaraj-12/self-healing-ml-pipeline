import json
from pathlib import Path

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
CANDIDATE_PATH = "artifacts/incidents/repair_candidates.jsonl"


def main():
    store = IncidentStore(INCIDENT_PATH)
    incidents = store.get_all()

    if not incidents:
        raise RuntimeError(
            "No incidents found. Run a failure experiment first."
        )

    # Use the most recently recorded incident.
    incident = incidents[-1]

    # Generate a diagnosis from the same incident.
    rca = RuleBasedRCA().analyze(incident)

    # Propose a repair; do not execute it.
    generator = RepairGenerator()
    candidate = generator.generate(incident, rca)

    path = Path(CANDIDATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(candidate.to_dict()) + "\n"
        )

    print("\nREPAIR CANDIDATE GENERATED")
    print("=" * 50)
    print(json.dumps(candidate.to_dict(), indent=2))
    print("\nNo changes have been applied to the pipeline.")


if __name__ == "__main__":
    main()