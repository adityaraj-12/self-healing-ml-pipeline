"""Run no-healing and retry-once control baselines without LLM API calls.

Persistent-fault baseline:
  * no_healing: one execution attempt with the configured fault injected.
  * retry_once: retry the same injected fault once after a non-zero exit.

Transient control:
  * inject a one-shot exception into the data-loading call; the retry arm
    invokes the pipeline a second time and should complete. This synthetic
    transient check is separate from the twelve persistent trial scenarios.

The output explicitly distinguishes these control experiments and does not
claim that repeated templates are independent real-world failures.
"""

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "benchmarks" / "results"
TRIAL_CASES_PATH = ROOT / "benchmarks" / "scenarios" / "trial_cases.yaml"
PIPELINE_CONFIG_PATH = ROOT / "configs" / "pipeline.yaml"


def load_cases():
    with TRIAL_CASES_PATH.open(encoding="utf-8") as file:
        return yaml.safe_load(file)["cases"]


def ensure_schema():
    # Establish the clean schema reference without needing an extra model run.
    from pipeline.ingestion import load_data
    from pipeline.schema_validation import save_schema

    with PIPELINE_CONFIG_PATH.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    x, _ = load_data()
    save_schema(x, config["artifacts"]["schema"])


def persistent_attempt(case, repeat_index, attempt_index):
    # Call the production runner in-process to avoid repeatedly importing the
    # large sklearn stack in child processes. run_pipeline reloads its YAML
    # configuration on every call, and the benchmark catches the expected
    # injected exception as a failed no-healing attempt.
    import pipeline.runner as runner

    started = perf_counter()
    stdout = io.StringIO()
    stderr = io.StringIO()
    error = None
    succeeded = False
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            runner.run_pipeline(
                failure_type=case["failure_type"],
                case_id=case["case_id"],
                repeat_index=repeat_index,
                auto_heal=False,
            )
        succeeded = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    return {
        "attempt": attempt_index,
        "exit_code": 0 if succeeded else 1,
        "elapsed_seconds": round(perf_counter() - started, 6),
        "pipeline_succeeded": succeeded,
        "error": error,
        "stderr_tail": stderr.getvalue()[-500:] if not succeeded else "",
    }


def run_persistent_baselines(cases, repeats):
    rows = []
    for case in cases:
        for repeat_index in range(repeats):
            first = persistent_attempt(case, repeat_index, 1)
            rows.append({
                "experiment": "persistent_injected_faults",
                "case_id": case["case_id"],
                "failure_type": case["failure_type"],
                "repeat_index": repeat_index,
                "method": "no_healing",
                "attempts": [first],
                "pipeline_succeeded": first["pipeline_succeeded"],
                "note": "No repair action is requested; injected fault remains active.",
            })

            attempts = [first]
            if not first["pipeline_succeeded"]:
                attempts.append(persistent_attempt(case, repeat_index, 2))
            succeeded = any(a["pipeline_succeeded"] for a in attempts)
            rows.append({
                "experiment": "persistent_injected_faults",
                "case_id": case["case_id"],
                "failure_type": case["failure_type"],
                "repeat_index": repeat_index,
                "method": "retry_once",
                "attempts": attempts,
                "pipeline_succeeded": succeeded,
                "note": "Retry repeats the same deterministic injected fault; it does not modify the input or configuration.",
            })
    return rows


def run_transient_trial(method, repeat_index):
    # Use the real pipeline orchestration with a benchmark-only one-shot
    # exception at the load_data boundary. No persistent state or network call
    # is required to make attempt 2 succeed.
    import pipeline.runner as runner

    original_load_data = runner.load_data
    state = {"calls": 0}

    def one_shot_transient_load():
        state["calls"] += 1
        if state["calls"] == 1:
            raise TimeoutError("Benchmark-injected one-shot transient load timeout")
        return original_load_data()

    runner.load_data = one_shot_transient_load
    attempts = []
    max_attempts = 1 if method == "no_healing" else 2
    try:
        for attempt_index in range(1, max_attempts + 1):
            started = perf_counter()
            stdout = io.StringIO()
            stderr = io.StringIO()
            succeeded = False
            error = None
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    runner.run_pipeline(auto_heal=False)
                succeeded = True
            except Exception as exc:  # expected for the first transient attempt
                error = f"{type(exc).__name__}: {exc}"
            attempts.append({
                "attempt": attempt_index,
                "pipeline_succeeded": succeeded,
                "elapsed_seconds": round(perf_counter() - started, 6),
                "error": error,
            })
            if succeeded:
                break
    finally:
        runner.load_data = original_load_data

    return {
        "experiment": "one_shot_transient_load_control",
        "case_id": "transient_load_timeout_once",
        "failure_type": "transient_load_timeout",
        "repeat_index": repeat_index,
        "method": method,
        "attempts": attempts,
        "pipeline_succeeded": any(a["pipeline_succeeded"] for a in attempts),
        "note": (
            "Benchmark-only one-shot load timeout. This is separate from the "
            "twelve configured persistent fault variants."
        ),
    }


def summarize(rows):
    summary = {}
    for experiment in sorted({row["experiment"] for row in rows}):
        summary[experiment] = {}
        subset = [row for row in rows if row["experiment"] == experiment]
        for method in sorted({row["method"] for row in subset}):
            group = [row for row in subset if row["method"] == method]
            succeeded = sum(row["pipeline_succeeded"] for row in group)
            summary[experiment][method] = {
                "trials": len(group),
                "pipeline_successes": succeeded,
                "pipeline_success_rate": succeeded / len(group) if group else None,
            }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--skip-transient-control", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    os.chdir(ROOT)
    ensure_schema()
    rows = run_persistent_baselines(load_cases(), args.repeats)
    if not args.skip_transient_control:
        for repeat_index in range(args.repeats):
            rows.append(run_transient_trial("no_healing", repeat_index))
            rows.append(run_transient_trial("retry_once", repeat_index))

    summary = summarize(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeats_per_persistent_scenario": args.repeats,
        "persistent_scenario_count": len(load_cases()),
        "persistent_trial_count_per_method": len(load_cases()) * args.repeats,
        "summary": summary,
        "interpretation": (
            "The persistent-fault controls measure whether doing nothing or repeating "
            "the same run resolves faults that remain injected. The transient load "
            "control separately verifies the expected behavior of a single retry for "
            "a one-shot error. These controls do not by themselves establish that a "
            "policy gate is necessary or sufficient."
        ),
        "results": rows,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"baseline_controls_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "output_path": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
