"""Evaluate the frozen rule-based detector/RCA on alternate fault signatures.

This is a synthetic, project-authored diagnostic stress test. It is not an
independent or production benchmark. The family detector is evaluated end to
end; the root-cause mapper receives the expected family and is evaluated only
for conditional subcode mapping.
"""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from healing.detector.failure_detector import FailureDetector
from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "data" / "failure_stress_challenge_v1.json"
DETECTOR_PATH = ROOT / "healing" / "detector" / "failure_detector.py"
RCA_PATH = ROOT / "healing" / "rca" / "rule_based_rca.py"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson(successes, n, z=1.959963984540054):
    if not n:
        return None
    p = successes / n
    z2 = z*z
    den = 1 + z2/n
    center = (p + z2/(2*n))/den
    half = z*math.sqrt(p*(1-p)/n + z2/(4*n*n))/den
    return [round(max(0, center-half), 4), round(min(1, center+half), 4)]


def make_exception(type_name, message):
    builtins = {
        "ValueError": ValueError, "KeyError": KeyError,
        "TypeError": TypeError, "ImportError": ImportError,
        "ModuleNotFoundError": ModuleNotFoundError,
        "FileNotFoundError": FileNotFoundError,
        "PermissionError": PermissionError, "TimeoutError": TimeoutError,
        "RuntimeError": RuntimeError, "OSError": OSError,
    }
    cls = builtins.get(type_name)
    if cls:
        return cls(message)
    # Keep custom exception names explicit if a case needs one in a later version.
    custom = type(type_name, (Exception,), {})
    return custom(message)


def macro_f1(rows, label_field, predicted_field):
    labels = sorted({row[label_field] for row in rows} | {row[predicted_field] for row in rows})
    scores = []
    for label in labels:
        tp = sum(row[label_field] == label and row[predicted_field] == label for row in rows)
        fp = sum(row[label_field] != label and row[predicted_field] == label for row in rows)
        fn = sum(row[label_field] == label and row[predicted_field] != label for row in rows)
        precision = tp/(tp+fp) if tp+fp else 0.0
        recall = tp/(tp+fn) if tp+fn else 0.0
        scores.append(2*precision*recall/(precision+recall) if precision+recall else 0.0)
    return sum(scores)/len(scores) if scores else None


def _resolve_output_path(output_path=None):
    if output_path is None:
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S_%fZ")
        day = now.strftime("%Y-%m-%d")
        path = ROOT / "research_artifacts" / day / f"failure_stress_challenge_v1_{stamp}.json"
    else:
        path = Path(output_path)
        if not path.is_absolute():
            path = ROOT / path
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing result: {path}. "
            "Choose a new output path to preserve historical evidence."
        )
    return path


def main(output_path=None):
    output_path = _resolve_output_path(output_path)
    fixture = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    detector = FailureDetector()
    rca = RuleBasedRCA()
    rows = []
    for case in fixture["cases"]:
        exc = make_exception(case["exception_type"], case["message"])
        detection = detector.detect(exc, {"runtime": {"current_stage": case["stage"]}})
        incident = type("IncidentLike", (), {
            "failure_type": case["expected_failure_family"],
            "error_message": case["message"],
        })()
        diagnosis = rca.analyze(incident)
        rows.append({
            **case,
            "detected_failure_family": detection["failure_type"],
            "detector_correct": detection["failure_type"] == case["expected_failure_family"],
            "detector_confidence": detection["confidence"],
            "predicted_root_cause_code": diagnosis.root_cause_code,
            "conditional_subcode_correct": diagnosis.root_cause_code == case["expected_root_cause_code"],
        })

    fam_counts = defaultdict(lambda: {"n": 0, "correct": 0})
    sub_counts = defaultdict(lambda: {"n": 0, "correct": 0})
    for row in rows:
        b = fam_counts[row["expected_failure_family"]]
        b["n"] += 1
        b["correct"] += int(row["detector_correct"])
        s = sub_counts[row["expected_failure_family"]]
        s["n"] += 1
        s["correct"] += int(row["conditional_subcode_correct"])
    for bucket in list(fam_counts.values()) + list(sub_counts.values()):
        bucket["accuracy"] = round(bucket["correct"] / bucket["n"], 4)

    n = len(rows)
    detector_ok = sum(row["detector_correct"] for row in rows)
    sub_ok = sum(row["conditional_subcode_correct"] for row in rows)
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": fixture["dataset_id"],
        "dataset_status": fixture["status"],
        "dataset_sha256": sha256(DATA_PATH),
        "detector_source_sha256": sha256(DETECTOR_PATH),
        "rca_source_sha256": sha256(RCA_PATH),
        "case_count": n,
        "family_detection": {
            "correct": detector_ok,
            "incorrect": n-detector_ok,
            "accuracy": round(detector_ok/n, 4),
            "wilson_95_descriptive": wilson(detector_ok, n),
            "macro_f1": round(macro_f1(rows, "expected_failure_family", "detected_failure_family"), 4),
            "per_family": dict(sorted(fam_counts.items())),
            "confusion_pairs": dict(sorted(Counter(f"{r['expected_failure_family']} -> {r['detected_failure_family']}" for r in rows).items())),
        },
        "conditional_root_cause_subcode": {
            "correct": sub_ok,
            "incorrect": n-sub_ok,
            "accuracy": round(sub_ok/n, 4),
            "wilson_95_descriptive": wilson(sub_ok, n),
            "per_supplied_family": dict(sorted(sub_counts.items())),
            "incorrect_cases": [r["case_id"] for r in rows if not r["conditional_subcode_correct"]],
        },
        "interpretation": (
            "A frozen, project-authored synthetic stress set of alternate signatures. It was run without tuning the implementation against these results, but cases are not independently sampled or externally annotated. The family detector is evaluated end-to-end. RuleBasedRCA receives the expected family, so subcode results are conditional and do not measure end-to-end RCA."
        ),
        "results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k != "results"}, indent=2))
    print(f"Output: {output_path}")
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="Optional output path; existing files are never overwritten.")
    args = parser.parse_args()
    try:
        main(output_path=args.output)
    except FileExistsError as exc:
        parser.error(str(exc))
