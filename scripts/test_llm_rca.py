from dotenv import load_dotenv

from healing.incidents.incident_store import IncidentStore
from healing.rca.rca_service import RCAService


load_dotenv()


store = IncidentStore(
    "artifacts/incidents/incidents.jsonl"
)

incidents = store.get_all()

if not incidents:
    raise RuntimeError(
        "No incidents found."
    )

incident = incidents[-1]

service = RCAService()

result = service.analyze_llm(
    incident
)

print("\nLLM RCA")
print("=" * 60)

print(
    f"Failure type: "
    f"{result.failure_type}"
)

print(
    f"Root cause: "
    f"{result.root_cause}"
)

print("\nEvidence:")

for item in result.evidence:
    print(f"- {item}")

print(
    f"\nRepair target: "
    f"{result.repair_target}"
)

print(
    f"Suggested action: "
    f"{result.suggested_action}"
)

print(
    f"Confidence: "
    f"{result.confidence:.2f}"
)