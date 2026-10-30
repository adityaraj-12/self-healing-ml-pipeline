"""Evaluate frozen rule-based RCA on a separately locked synthetic case set.

The source hash must match the value stored in benchmarks/data/rca_locked_v1.json.
This is a developer-authored synthetic holdout, not an external blind benchmark.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "data" / "rca_locked_v1.json"
RESULT_DIR = ROOT / "benchmarks" / "results"
SOURCE_PATH = ROOT / "healing" / "rca" / "rule_based_rca.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wilson(successes: int, total: int, z: float = 1.959963984540054):
    if total == 0:
        return None
    p = successes / total
    z2 = z * z
    den = 1 + z2 / total
    center = (p + z2 / (2 * total)) / den
    half = z * ((p * (1 - p) / total) + z2 / (4 * total * total)) ** 0.5 / den
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-source-mismatch", action="store_true",
                        help="Run for exploration despite a changed RCA implementation hash.")
    args = parser.parse_args()

    fixture = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    actual_source_hash = sha256(SOURCE_PATH)
    expected_source_hash = fixture["rule_implementation_sha256"]
    if actual_source_hash != expected_source_hash and not args.allow_source_mismatch:
        raise SystemExit(
            "Frozen RCA implementation hash mismatch. Do not tune on the locked set; "
            "create a new versioned set if the code intentionally changes. "
            f"Expected {expected_source_hash}, got {actual_source_hash}."
        )

    rca = RuleBasedRCA()
    rows = []
    by_type = defaultdict(lambda: {"cases": 0, "correct": 0})
    for case in fixture["cases"]:
        incident = SimpleNamespace(
            incident_id=f"RCA-LOCKED-{case['case_id']}",
            failure_type=case["failure_type"],
            error_message=case["error_message"],
        )
        actual = rca.analyze(incident).root_cause_code
        expected = case["expected_root_cause_code"]
        row = {
            **case,
            "predicted_root_cause_code": actual,
            "correct": actual == expected,
        }
        rows.append(row)
        bucket = by_type[case["failure_type"]]
        bucket["cases"] += 1
        bucket["correct"] += int(row["correct"])

    n = len(rows)
    correct = sum(row["correct"] for row in rows)
    incorrect = [row for row in rows if not row["correct"]]
    for values in by_type.values():
        values["accuracy"] = round(values["correct"] / values["cases"], 4)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": fixture["dataset_id"],
        "dataset_sha256": sha256(DATA_PATH),
        "rule_implementation_sha256": actual_source_hash,
        "source_hash_matched_lock": actual_source_hash == expected_source_hash,
        "case_count": n,
        "correct": correct,
        "incorrect": n - correct,
        "accuracy": round(correct / n, 4) if n else None,
        "wilson_95_trial_level_descriptive": wilson(correct, n),
        "by_failure_type": dict(sorted(by_type.items())),
        "independence_note": fixture["independence_note"],
        "interpretation": (
            "This is a locked developer-authored synthetic evaluation, separate from the configured trial cases and prior challenge scripts. "
            "It is not third-party blind and is not a production accuracy estimate. The interval is descriptive and does not model case-design uncertainty."
        ),
        "incorrect_cases": incorrect,
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULT_DIR / f"diagnosis_locked_v1_{timestamp}.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k not in {"results", "incorrect_cases"}}, indent=2))
    print("\nIncorrect cases:")
    for row in incorrect:
        print(f"- {row['case_id']}: expected={row['expected_root_cause_code']!r}; predicted={row['predicted_root_cause_code']!r}")
    print(f"\nFull trial-level output: {out_path}")


if __name__ == "__main__":
    main()
