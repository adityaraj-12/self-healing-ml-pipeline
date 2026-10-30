"""Evaluate frozen rule-based RCA on externally sourced public issue excerpts.

This is an exploratory post-hoc probe, not a blind or representative benchmark.
The coarse ``failure_type`` is supplied, so the test measures subcode mapping,
not end-to-end failure-family detection.
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
DATA_PATH = ROOT / "benchmarks" / "data" / "rca_public_issue_probe_v1.json"
SOURCE_PATH = ROOT / "healing" / "rca" / "rule_based_rca.py"
RESULT_DIR = ROOT / "benchmarks" / "results"
EXPECTED_RULE_HASH = "00a0dc340102408c5a2dc0ff430c25691795f9b551197eefee49caf3131a6164"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-source-mismatch",
        action="store_true",
        help="Run exploratorily when the RCA implementation has changed; output remains post-hoc and is not the locked evaluation.",
    )
    args = parser.parse_args()

    actual_hash = sha256(SOURCE_PATH)
    if actual_hash != EXPECTED_RULE_HASH and not args.allow_source_mismatch:
        raise SystemExit(
            "RCA implementation hash mismatch. Keep the original output and create a versioned probe for the changed implementation. "
            f"Expected {EXPECTED_RULE_HASH}, got {actual_hash}."
        )

    fixture = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rca = RuleBasedRCA()
    rows = []
    buckets = defaultdict(lambda: {"cases": 0, "correct": 0})
    for case in fixture["cases"]:
        incident = SimpleNamespace(
            incident_id=f"RCA-PUBLIC-{case['case_id']}",
            failure_type=case["failure_type"],
            error_message=case["error_message"],
        )
        predicted = rca.analyze(incident).root_cause_code
        correct = predicted == case["expected_root_cause_code"]
        rows.append({
            **case,
            "predicted_root_cause_code": predicted,
            "correct": correct,
        })
        bucket = buckets[case["failure_type"]]
        bucket["cases"] += 1
        bucket["correct"] += int(correct)

    for bucket in buckets.values():
        bucket["accuracy"] = round(bucket["correct"] / bucket["cases"], 4)

    correct = sum(row["correct"] for row in rows)
    total = len(rows)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": fixture["dataset_id"],
        "dataset_sha256": sha256(DATA_PATH),
        "rule_implementation_sha256": actual_hash,
        "source_hash_matched_expected": actual_hash == EXPECTED_RULE_HASH,
        "total_cases": total,
        "correct": correct,
        "incorrect": total - correct,
        "accuracy": round(correct / total, 4) if total else None,
        "by_failure_type": dict(sorted(buckets.items())),
        "interpretation": (
            "Post-hoc exploratory probe based on public project issue reports and one official source-code excerpt. "
            "The cases were manually curated after the RCA implementation existed; they are not blind, independently labelled, "
            "or representative of production ML incidents. A coarse failure_type is supplied for every case, so these results "
            "measure conditional subcode mapping rather than end-to-end detection."
        ),
        "errors": [row for row in rows if not row["correct"]],
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULT_DIR / "rca_public_issue_probe_v1_result.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in output.items() if key not in {"results", "errors"}}
    print(json.dumps(summary, indent=2))
    print("\nMisclassified cases:")
    for row in output["errors"]:
        print(f"- {row['case_id']}: expected={row['expected_root_cause_code']!r}; predicted={row['predicted_root_cause_code']!r}; source={row['source_url']}")
    print(f"\nDetailed result: {out_path}")


if __name__ == "__main__":
    main()
