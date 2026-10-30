"""Run the developer-authored failure-family regression set.

This is a versioned regression harness, not an independent or blind benchmark.
The cases and the classifier were developed within the same project.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from healing.detector.failure_detector import FailureDetector

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "data" / "failure_family_regression_v1.json"
DETECTOR_PATH = ROOT / "healing" / "detector" / "failure_detector.py"
RESULT_DIR = ROOT / "benchmarks" / "results"

class InvalidParameterError(Exception):
    """Small stand-in for estimators that expose this exception class."""

class JSONDecodeErrorForRegression(ValueError):
    """Keep exception-name testing explicit without requiring a real JSON parse."""

EXCEPTION_CLASSES = {
    "ValueError": ValueError,
    "TypeError": TypeError,
    "InvalidParameterError": InvalidParameterError,
    "ModuleNotFoundError": ModuleNotFoundError,
    "ImportError": ImportError,
    "OSError": OSError,
    "RuntimeError": RuntimeError,
    "FileNotFoundError": FileNotFoundError,
    "KeyError": KeyError,
    "PermissionError": PermissionError,
    "TimeoutError": TimeoutError,
    "MemoryError": MemoryError,
    "JSONDecodeError": type("JSONDecodeError", (ValueError,), {}),
    "ConnectionError": ConnectionError,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_case(detector, case):
    if case["exception_type"] not in EXCEPTION_CLASSES:
        raise ValueError(f"Unsupported exception type: {case['exception_type']}")
    exception = EXCEPTION_CLASSES[case["exception_type"]](case["message"])
    context = {"runtime": {"current_stage": case.get("stage", "")}}
    return detector.detect(exception, context)


def calculate_metrics(rows):
    labels = sorted({row["expected"] for row in rows} | {row["predicted"] for row in rows})
    per_class = {}
    for label in labels:
        tp = sum(row["expected"] == label and row["predicted"] == label for row in rows)
        fp = sum(row["expected"] != label and row["predicted"] == label for row in rows)
        fn = sum(row["expected"] == label and row["predicted"] != label for row in rows)
        support = sum(row["expected"] == label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        per_class[label] = {
            "support": support,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    correct = sum(row["correct"] for row in rows)
    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(per_class) if per_class else 0.0
    return {
        "case_count": len(rows),
        "correct": correct,
        "incorrect": len(rows) - correct,
        "accuracy": round(correct / len(rows), 4) if rows else None,
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-source-mismatch",
        action="store_true",
        help="Run exploratory analysis after the detector implementation has changed.",
    )
    args = parser.parse_args()
    fixture = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    current_hash = sha256(DETECTOR_PATH)
    expected_hash = fixture.get("detector_implementation_sha256")
    if expected_hash and current_hash != expected_hash and not args.allow_source_mismatch:
        raise SystemExit(
            "Detector implementation hash differs from the versioned fixture. "
            "Do not present this run as the locked regression result. Create a new "
            "fixture version or pass --allow-source-mismatch for exploration."
        )

    detector = FailureDetector()
    rows = []
    for case in fixture["cases"]:
        prediction = classify_case(detector, case)
        rows.append({
            "case_id": case["case_id"],
            "stage": case.get("stage", ""),
            "exception_type": case["exception_type"],
            "message": case["message"],
            "expected": case["expected"],
            "predicted": prediction["failure_type"],
            "confidence": prediction["confidence"],
            "correct": prediction["failure_type"] == case["expected"],
            "reason": prediction["reason"],
        })

    summary = calculate_metrics(rows)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": fixture["dataset_id"],
        "dataset_sha256": sha256(DATA_PATH),
        "detector_implementation_sha256": current_hash,
        "source_hash_matched_lock": bool(expected_hash and current_hash == expected_hash),
        "purpose": fixture["purpose"],
        "selection_note": fixture["selection_note"],
        "interpretation": (
            "Developer-authored regression results only. The fixture was designed with this project and is not an independent, blind, or production evaluation. "
            "Do not use it as a generalization estimate or as a substitute for external annotation."
        ),
        **summary,
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"failure_family_regression_v1_{timestamp}.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "results"}, indent=2))
    print(f"\nDetailed output: {output_path}")
    print("\nIncorrect cases:")
    incorrect = [row for row in rows if not row["correct"]]
    for row in incorrect:
        print(f"- {row['case_id']}: expected={row['expected']}; predicted={row['predicted']}")


if __name__ == "__main__":
    main()
