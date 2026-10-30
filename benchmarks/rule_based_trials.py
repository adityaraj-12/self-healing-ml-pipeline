"""Rerun deterministic policy-gated recovery across configured stress trials.

This script makes no LLM API calls. It measures the rule-based gated method
using the current scenario fixture and a configurable repetition count. The
historical LLM comparison was run on the earlier twelve-variant fixture.
"""

import argparse
import contextlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"
PIPELINE_CONFIG = ROOT / "configs" / "pipeline.yaml"
TRIAL_CASES = ROOT / "benchmarks" / "scenarios" / "trial_cases.yaml"


def prepare_schema():
    from pipeline.ingestion import load_data
    from pipeline.schema_validation import save_schema

    with PIPELINE_CONFIG.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    x, _ = load_data()
    save_schema(x, config["artifacts"]["schema"])


def load_cases():
    with TRIAL_CASES.open(encoding="utf-8") as file:
        return yaml.safe_load(file)["cases"]


def wilson_interval(successes, total, z=1.959963984540054):
    if total <= 0:
        return None
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    half = z * ((p * (1 - p) / total) + z2 / (4 * total * total)) ** 0.5 / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    os.chdir(ROOT)
    prepare_schema()
    import pipeline.runner as runner

    rows = []
    cases = load_cases()
    for case_index, case in enumerate(cases, start=1):
        for repeat_index in range(args.repeats):
            started = perf_counter()
            stdout = io.StringIO()
            stderr = io.StringIO()
            raised_error = None
            result = None
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = runner.run_pipeline(
                        failure_type=case["failure_type"],
                        case_id=case["case_id"],
                        repeat_index=repeat_index,
                        auto_heal=True,
                    )
            except Exception as exc:
                raised_error = f"{type(exc).__name__}: {exc}"

            if not isinstance(result, dict):
                result = {}
            validation = result.get("validation_report") or {}
            candidate = result.get("candidate") or {}
            rca = result.get("rca") or {}
            rows.append({
                "case_id": case["case_id"],
                "failure_type": case["failure_type"],
                "repeat_index": repeat_index,
                "method": "rule_based_gated",
                "status": result.get("status", "runner_error" if raised_error else "missing_result"),
                "rca_root_cause_code": rca.get("root_cause_code"),
                "candidate_action": candidate.get("action") if isinstance(candidate, dict) else None,
                "validation_status": validation.get("status") if isinstance(validation, dict) else None,
                "duration_seconds": round(perf_counter() - started, 6),
                "raised_error": raised_error,
                "post_recovery_check": (
                    (result.get("recovery_result") or {}).get("post_recovery_check")
                    if isinstance(result.get("recovery_result"), dict) else None
                ),
            })
        print(f"Completed scenario family {case_index}/{len(cases)}: {case['case_id']}", flush=True)

    recovered = sum(row["status"] == "recovered" for row in rows)
    human_review = sum(row["status"] == "needs_human_approval" for row in rows)
    blocked_or_failed = sum(row["status"] not in {"recovered", "needs_human_approval"} for row in rows)
    eligible = [row for row in rows if row["status"] != "needs_human_approval"]
    eligible_recovered = sum(row["status"] == "recovered" for row in eligible)
    durations = [row["duration_seconds"] for row in rows]

    by_failure = {}
    for failure_type in sorted({row["failure_type"] for row in rows}):
        group = [row for row in rows if row["failure_type"] == failure_type]
        by_failure[failure_type] = {
            "trials": len(group),
            "recovered": sum(row["status"] == "recovered" for row in group),
            "human_review": sum(row["status"] == "needs_human_approval" for row in group),
            "blocked_or_failed": sum(row["status"] not in {"recovered", "needs_human_approval"} for row in group),
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "rule_based_gated",
        "scenario_variants": len(cases),
        "repeats_per_scenario": args.repeats,
        "trials": len(rows),
        "recovered": recovered,
        "overall_recovery_rate": recovered / len(rows) if rows else None,
        "overall_recovery_wilson_95": wilson_interval(recovered, len(rows)),
        "automatically_eligible_trials": len(eligible),
        "eligible_recovered": eligible_recovered,
        "eligible_recovery_rate": eligible_recovered / len(eligible) if eligible else None,
        "eligible_recovery_wilson_95": wilson_interval(eligible_recovered, len(eligible)),
        "human_review": human_review,
        "blocked_or_failed": blocked_or_failed,
        "mean_trial_duration_seconds": mean(durations) if durations else None,
        "median_trial_duration_seconds": median(durations) if durations else None,
        "by_failure_type": by_failure,
        "interpretation": (
            "This is a fresh, non-LLM run of the deterministic gated pathway. "
            "It does not reproduce the LLM comparison or isolate policy-gate causality. "
            f"Repeated trials reuse {len(cases)} fixed scenario templates, so Wilson intervals are descriptive only and should not be interpreted as population-level uncertainty."
        ),
        "results": rows,
    }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"rule_based_trials_{timestamp}.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    print(f"\nRule-based trial report saved to: {output_path}")


if __name__ == "__main__":
    main()
