import json
from pathlib import Path


class RCAStore:

    def __init__(self, path):
        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def save(self, rca_result):

        with open(
            self.path,
            "a"
        ) as f:

            f.write(
                json.dumps(
                    rca_result.to_dict()
                ) + "\n"
            )