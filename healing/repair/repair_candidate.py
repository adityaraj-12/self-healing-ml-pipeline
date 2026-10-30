from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any


@dataclass
class RepairCandidate:
    candidate_id: str
    incident_id: str
    created_at: str

    failure_type: str
    action: str
    target: str

    parameters: dict[str, Any]
    rationale: str
    evidence: list[str]

    validation_checks: list[str]
    risks: list[str]

    requires_human_approval: bool
    status: str = "proposed"
    generator: str = "rule_based"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def create(cls, incident, plan):
        return cls(
            candidate_id=f"RC-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),

            failure_type=incident.failure_type,
            action=plan["action"],
            target=plan["target"],

            parameters=plan["parameters"],
            rationale=plan["rationale"],
            evidence=plan["evidence"],

            validation_checks=plan["validation_checks"],
            risks=plan["risks"],

            requires_human_approval=plan[
                "requires_human_approval"
            ],

            status="proposed",
            generator=plan.get("generator", "rule_based")
        )