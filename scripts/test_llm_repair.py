import json
from pathlib import Path

from dotenv import load_dotenv

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.llm_repair_generator import LLMRepairGenerator


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
OUTPUT_PATH = "artifacts/incidents/llm_repair_candidates.jsonl"


def main():
    load_dotenv()

    incidents = IncidentStore(
        INCIDENT_PATH
    ).get_all()

    if not incidents:
        raise RuntimeError(
            "No incidents found. Run a failure experiment first."
        )

    incident = incidents[-1]

    # Initially, keep RCA constant so that we isolate the
    # difference caused by the repair generator.
    rca = RuleBasedRCA().analyze(incident)

    generator = LLMRepairGenerator()

    candidate = generator.generate(
        incident,
        rca
    )

    record = candidate.to_dict()

    output = Path(OUTPUT_PATH)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print("\nLLM REPAIR CANDIDATE")
    print("=" * 60)
    print(json.dumps(record, indent=2))
    print("\nNo repair has been executed.")


if __name__ == "__main__":
    main()