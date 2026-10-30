import json
import subprocess
import sys
import time

from datetime import datetime, timezone
from pathlib import Path

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine

from benchmarks.metrics import summarize_results


ROOT = Path(__file__).resolve().parents[1]

FAILURE_TYPES = [
    "schema_change",
    "data_quality",
    "configuration_error",
    "dependency_error",
]

INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
CANDIDATE_PATH = "artifacts/incidents/repair_candidates.jsonl"
VALIDATION_PATH = "artifacts/incidents/validation_results.jsonl"
RECOVERY_PATH = "artifacts/incidents/recovery_results.jsonl"


def append_jsonl(path, record):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def run_command(args):
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False
    )


def run_healthy_baseline():
    print("\nPreparing healthy baseline...")

    result = run_command([
        sys.executable,
        "-m",
        "pipeline.runner"
    ])

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)

        raise RuntimeError(
            "Healthy pipeline failed. Fix it before benchmarking."
        )

    print("Healthy baseline completed.")


def run_scenario(failure_type):
    print("\n" + "=" * 65)
    print(f"Running benchmark: {failure_type}")
    print("=" * 65)

    started = time.perf_counter()

    store = IncidentStore(
        str(ROOT / INCIDENT_PATH)
    )

    old_incidents = store.get_all()
    old_count = len(old_incidents)

    # -------------------------------------------------
    # 1. Run the pipeline with a controlled failure.
    # -------------------------------------------------

    pipeline_result = run_command([
        sys.executable,
        "-m",
        "pipeline.runner",
        "--failure",
        failure_type
    ])

    record = {
        "failure_type": failure_type,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "pipeline_exit_code": pipeline_result.returncode,
        "failure_run_seconds": None,

        "incident_created": False,
        "detected_failure_type": None,
        "detection_correct": False,
        "monitor_elapsed_seconds": None,

        "candidate_generated": False,
        "candidate_action": None,

        "validation_status": "not_run",
        "validation_duration_seconds": None,

        "recovery_status": "not_attempted",
        "recovery_duration_seconds": None,

        "overall_experiment_seconds": None,
    }

    record["failure_run_seconds"] = round(
        time.perf_counter() - started, 4
    )

    # A nonzero pipeline exit is expected for injected failures.
    # We still require evidence that the detector created an incident.

    all_incidents = store.get_all()
    new_incidents = all_incidents[old_count:]

    if not new_incidents:
        record["failure_run_error"] = (
            "No new incident was recorded."
        )

        record["overall_experiment_seconds"] = round(
            time.perf_counter() - started, 4
        )

        return record

    incident = new_incidents[-1]

    record["incident_created"] = True
    record["incident_id"] = incident.incident_id
    record["detected_failure_type"] = incident.failure_type

    record["detection_correct"] = (
        incident.failure_type == failure_type
    )

    runtime = incident.context.get("runtime", {})

    record["monitor_elapsed_seconds"] = runtime.get(
        "elapsed_seconds"
    )

    # -------------------------------------------------
    # 2. Root-cause analysis and repair generation.
    # -------------------------------------------------

    try:
        rca = RuleBasedRCA().analyze(incident)

        candidate = RepairGenerator().generate(
            incident,
            rca
        ).to_dict()

        append_jsonl(CANDIDATE_PATH, candidate)

        record["candidate_generated"] = True
        record["candidate_id"] = candidate["candidate_id"]
        record["candidate_action"] = candidate["action"]

    except Exception as exc:
        record["repair_generation_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

        record["overall_experiment_seconds"] = round(
            time.perf_counter() - started, 4
        )

        return record

    # -------------------------------------------------
    # 3. Sandbox validation.
    # -------------------------------------------------

    try:
        validator = RepairValidator()

        validation = validator.validate(
            candidate,
            incident
        )

        validator.save_report(
            validation,
            str(ROOT / VALIDATION_PATH)
        )

        record["validation_status"] = validation.get(
            "status", "unknown"
        )

        record["validation_duration_seconds"] = validation.get(
            "duration_seconds"
        )

    except Exception as exc:
        record["validation_status"] = "error"
        record["validation_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

        record["overall_experiment_seconds"] = round(
            time.perf_counter() - started, 4
        )

        return record

    # -------------------------------------------------
    # 4. Recovery only when validation passes.
    # -------------------------------------------------

    if record["validation_status"] == "passed":
        try:
            engine = RecoveryEngine()

            recovery = engine.recover(
                incident,
                candidate,
                validation
            )

            engine.save_result(
                recovery,
                str(ROOT / RECOVERY_PATH)
            )

            record["recovery_status"] = recovery.get(
                "status", "unknown"
            )

            record["recovery_duration_seconds"] = recovery.get(
                "duration_seconds"
            )

            record["recovered_metrics"] = recovery.get(
                "metrics"
            )

        except Exception as exc:
            record["recovery_status"] = "error"
            record["recovery_error"] = (
                f"{type(exc).__name__}: {exc}"
            )

    elif record["validation_status"] == "needs_human_approval":
        record["recovery_status"] = "needs_human_approval"

    else:
        record["recovery_status"] = "blocked"

    record["overall_experiment_seconds"] = round(
        time.perf_counter() - started, 4
    )

    print(
        "Detected:",
        record["detected_failure_type"]
    )

    print(
        "Validation:",
        record["validation_status"]
    )

    print(
        "Recovery:",
        record["recovery_status"]
    )

    return record


def main():
    run_healthy_baseline()

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    result_dir = ROOT / "benchmarks" / "results"
    result_dir.mkdir(parents=True, exist_ok=True)

    run_path = result_dir / f"run_{timestamp}.jsonl"
    summary_path = result_dir / f"summary_{timestamp}.json"

    records = []

    for failure_type in FAILURE_TYPES:
        record = run_scenario(failure_type)
        records.append(record)
        append_jsonl(str(run_path.relative_to(ROOT)), record)

    summary = summarize_results(records)

    with summary_path.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(summary, file, indent=2)

    print("\n" + "=" * 65)
    print("BENCHMARK SUMMARY")
    print("=" * 65)
    print(json.dumps(summary, indent=2))

    print(f"\nDetailed results: {run_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()