import json
from pathlib import Path


def get_schema(x):
    return {
        "columns": list(x.columns),
        "dtypes": {
            col: str(dtype)
            for col, dtype in x.dtypes.items()
        },
        "num_columns": len(x.columns)
    }


def save_schema(x, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    schema = get_schema(x)

    with open(path, "w") as f:
        json.dump(schema, f, indent=2)


def load_schema(path):
    with open(path, "r") as f:
        return json.load(f)


def validate_schema(x, path):
    expected = load_schema(path)

    actual_columns = list(x.columns)
    expected_columns = expected["columns"]

    missing = [
        col for col in expected_columns
        if col not in actual_columns
    ]

    unexpected = [
        col for col in actual_columns
        if col not in expected_columns
    ]

    if missing or unexpected:
        raise ValueError(
            "Schema mismatch | "
            f"missing={missing} | "
            f"unexpected={unexpected}"
        )

    return True