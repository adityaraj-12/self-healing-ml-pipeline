from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
import json


@dataclass
class Incident:
    incident_id: str
    timestamp: str

    failure_type: str
    confidence: float

    stage: str

    exception_type: str
    error_message: str

    severity: str

    pipeline_config: dict[str, Any]
    context: dict[str, Any]

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)