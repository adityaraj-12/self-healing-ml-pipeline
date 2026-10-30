import json
from pathlib import Path

from .incident import Incident


class IncidentStore:

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def save(self, incident: Incident):
        with open(self.path, "a") as f:
            f.write(
                json.dumps(
                    incident.to_dict()
                ) + "\n"
            )

    def get_all(self):
        if not self.path.exists():
            return []

        incidents = []

        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                data = json.loads(line)

                incidents.append(
                    Incident(**data)
                )

        return incidents