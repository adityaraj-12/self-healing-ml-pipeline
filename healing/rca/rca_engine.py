from dataclasses import dataclass, asdict
from typing import Any
import json


@dataclass
class RCAResult:
    failure_type: str
    root_cause: str
    evidence: list[str]
    repair_target: str
    suggested_action: str
    confidence: float
    method: str
    root_cause_code: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2
        )