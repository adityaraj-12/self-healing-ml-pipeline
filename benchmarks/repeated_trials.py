import argparse
import json
import os
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import yaml
from dotenv import load_dotenv

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.repair.llm_repair_generator import LLMRepairGenerator
from healing.repair.repair_policy import enforce_repair_policy
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine

from benchmarks.direct_llm_baseline import DirectLLMBaseline
from benchmarks.llm_run_manifest import write_manifest
from benchmarks.experiment_runtime import (
    ProviderQuotaExhausted,
    ProviderRateLimitDeferred,
    progress,
    run_with_rate_limit_retry,
    safe_error_summary,
)

ROOT = Path(__file__).resolve().parents[1]

INCIDENT_PATH = ROOT / "artifacts/incidents/incidents.jsonl"
RESULT_DIR = ROOT / "benchmarks/results"

VALIDATION_PATH = (
    ROOT / "artifacts/incidents/comparison_validation.jsonl"
)

RECOVERY_PATH = (
    ROOT / "artifacts/incidents/comparison_recovery.jsonl"
)

CANDIDATE_PATH = (
    ROOT / "artifacts/incidents/llm_repair_candidates.jsonl"
)

def read_cases():
    with open(
        ROOT / "benchmarks/scenarios/trial_cases.yaml",
        "r",
        encoding="utf-8"
    ) as f:
        return yaml.safe_load(f)["cases"]


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def run_pipeline_case(case, repeat_index=0):
    store = IncidentStore(str(INCIDENT_PATH))
    previous_ids = {
        item.incident_id
        for item in store.get_all()
    }

    started = perf_counter()

    completed = subprocess.run(
        [
            sys.executable,
            "-m", "pipeline.runner",
            "--failure", case["failure_type"],
            "--case-id", case["case_id"],
            "--repeat-index",
            str(repeat_index)
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False
    )

    elapsed = perf_counter() - started

    current = store.get_all()

    new_incidents = [
        item for item in current
        if item.incident_id not in previous_ids
    ]

    if not new_incidents:
        raise RuntimeError(
            f"{case['case_id']} created no incident. "
            f"Exit code: {completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )

    # The pipeline is expected to fail for these tests.
    incident = new_incidents[-1]

    if incident.failure_type != case["failure_type"]:
        raise RuntimeError(
            f"{case['case_id']}: expected "
            f"{case['failure_type']}, detected "
            f"{incident.failure_type}"
        )

    if (
        incident.context.get("failure_injection", {})
        .get("case_id") != case["case_id"]
    ):
        raise RuntimeError(
            f"{case['case_id']}: case ID was not preserved "
            "in the incident context."
        )

    return incident, elapsed


def run_gated(candidate, incident):
    started = perf_counter()

    try:
        validator = RepairValidator()

        validation = validator.validate(
            candidate,
            incident
        )

        validator.save_report(
            validation,
            str(VALIDATION_PATH)
        )

        status = validation.get("status", "unknown")

        if status != "passed":
            result = {
                "status": status,
                "validation_status": status,
                "validation_seconds": validation.get(
                    "duration_seconds"
                )
            }

        elif candidate.get("requires_human_approval", False):
            result = {
                "status": "needs_human_approval",
                "validation_status": "passed",
                "validation_seconds": validation.get(
                    "duration_seconds"
                )
            }

        else:
            engine = RecoveryEngine()

            recovery = engine.recover(
                incident,
                candidate,
                validation
            )

            engine.save_result(
                recovery,
                str(RECOVERY_PATH)
            )

            result = {
                "status": recovery.get("status"),
                "validation_status": "passed",
                "validation_seconds": validation.get(
                    "duration_seconds"
                ),
                "recovery_seconds": recovery.get(
                    "duration_seconds"
                ),
                "metrics": recovery.get("metrics"),
                "error": recovery.get("error")
            }

    except Exception as exc:
        result = {
            "status": "error",
            "error": safe_error_summary(exc)
        }

    result["method_duration_seconds"] = round(
        perf_counter() - started, 6
    )

    return result


def run_direct(candidate, incident):
    started = perf_counter()

    try:
        result = DirectLLMBaseline().run(
            candidate,
            incident
        )
    except Exception as exc:
        result = {
            "status": "error",
            "error": safe_error_summary(exc)
        }

    result["method_duration_seconds"] = round(
        perf_counter() - started, 6
    )

    return result


def generate_llm_candidate(
    incident,
    rca,
    max_rate_limit_attempts=4,
    max_rate_limit_wait_seconds=30.0,
):
    generator = LLMRepairGenerator()

    candidate_obj = run_with_rate_limit_retry(
        lambda: generator.generate(incident, rca),
        max_attempts=max_rate_limit_attempts,
        max_wait_seconds=max_rate_limit_wait_seconds,
    )

    candidate = candidate_obj.to_dict()

    # System policy decides approval, not the LLM.
    candidate = enforce_repair_policy(candidate)

    append_jsonl(CANDIDATE_PATH, candidate)

    return candidate



def evaluate_case(
    case,
    repeat_index=0,
    case_position=1,
    planned_case_executions=1,
    planned_repeats=1,
    max_rate_limit_attempts=4,
    max_rate_limit_wait_seconds=30.0,
):
    progress(
        f"CASE {case_position}/{planned_case_executions} | "
        f"{case['case_id']} | family={case['failure_type']} | "
        f"repeat={repeat_index + 1}/{planned_repeats}"
    )
    case_started = perf_counter()

    progress("STEP 1/6 | Injecting the configured fault and collecting the incident.")
    incident, failure_run_seconds = run_pipeline_case(case, repeat_index)
    progress(
        f"STEP 1/6 COMPLETE | incident={incident.incident_id} | "
        f"detected_family={incident.failure_type} | elapsed={failure_run_seconds:.3f}s"
    )

    progress("STEP 2/6 | Running rule-based root-cause analysis.")
    rca = RuleBasedRCA().analyze(incident)
    progress(
        f"STEP 2/6 COMPLETE | root_cause={getattr(rca, 'root_cause_code', 'unknown')}"
    )

    ground_truth = (
        incident.context
        .get("failure_injection", {})
        .get("ground_truth", {})
    )

    expected_root_cause = ground_truth.get(
        "root_cause_code"
    )

    predicted_root_cause = rca.root_cause_code

    diagnosis_correct = (
        predicted_root_cause == expected_root_cause
        if expected_root_cause is not None
        else None
    )

    # Candidate A: deterministic repair planner.
    progress("STEP 3/6 | Planning the deterministic rule-based repair candidate.")
    rule_planning_started = perf_counter()

    rule_candidate = enforce_repair_policy(
        RepairGenerator().generate(
            incident,
            rca
        ).to_dict()
    )

    rule_planning_seconds = round(
        perf_counter() - rule_planning_started,
        6
    )
    progress(
        f"STEP 3/6 COMPLETE | action={rule_candidate.get('action')} | "
        f"planning={rule_planning_seconds:.6f}s"
    )

    # Candidate B/C: share the same generated LLM candidate between both arms.
    llm_generation_started = perf_counter()
    progress(
        f"STEP 4/6 | Requesting an LLM repair candidate | "
        f"model={os.getenv('OPENAI_MODEL', '<not-configured>')}"
    )

    stop_after_case = False
    llm_stop_status = None
    try:
        llm_candidate = generate_llm_candidate(
            incident,
            rca,
            max_rate_limit_attempts=max_rate_limit_attempts,
            max_rate_limit_wait_seconds=max_rate_limit_wait_seconds,
        )
    except ProviderQuotaExhausted as exc:
        llm_candidate = None
        llm_error = str(exc)
        llm_stop_status = "provider_quota_exhausted"
        stop_after_case = True
    except ProviderRateLimitDeferred as exc:
        llm_candidate = None
        llm_error = str(exc)
        llm_stop_status = "provider_rate_limit_deferred"
        stop_after_case = True
    except Exception as exc:
        llm_candidate = None
        llm_error = safe_error_summary(exc)
    else:
        llm_error = None
    finally:
        llm_generation_seconds = round(
            perf_counter() - llm_generation_started,
            6
        )

    if llm_candidate is not None:
        progress(
            f"STEP 4/6 COMPLETE | candidate={llm_candidate.get('candidate_id')} | "
            f"action={llm_candidate.get('action')} | "
            f"generation={llm_generation_seconds:.3f}s"
        )
    elif stop_after_case:
        progress(
            f"STEP 4/6 STOPPED | {llm_stop_status}: {llm_error}",
            "ERROR",
        )
    else:
        progress(
            f"STEP 4/6 FAILED | candidate generation failed: {llm_error}",
            "ERROR",
        )


    rows = []

    methods = [
        (
            "rule_based_gated",
            rule_candidate,
            run_gated
        )
    ]

    if llm_candidate is not None:
        methods.extend([
            (
                "llm_direct_isolated",
                llm_candidate,
                run_direct
            ),
            (
                "llm_validated",
                llm_candidate,
                run_gated
            )
        ])
    else:
        for method in (
            "llm_direct_isolated",
            "llm_validated"
        ):
            rows.append({
                "case_id": case["case_id"],
                "incident_id": incident.incident_id,
                "failure_type": case["failure_type"],
                "method": method,
                "result": {
                    "status": llm_stop_status or "candidate_generation_failed",
                    "failure_kind": (
                        "provider_daily_quota"
                        if llm_stop_status == "provider_quota_exhausted"
                        else "provider_rate_limit_deferred"
                        if llm_stop_status == "provider_rate_limit_deferred"
                        else "candidate_generation"
                    ),
                    "error": llm_error,
                    "repeat_index": repeat_index,
                },
                "llm_generation_seconds": llm_generation_seconds,
            })

    progress("STEP 5/6 | Evaluating repair paths; dependency changes remain review-only.")
    for method, candidate, run_method in methods:
        progress(f"  METHOD START | {method} | candidate_action={candidate.get('action')}")
        result = run_method(
            candidate,
            incident
        )

        rows.append({
            "case_id": case["case_id"],
            "incident_id": incident.incident_id,
            "failure_type": case["failure_type"],
            "method": method,
            "candidate_id": candidate["candidate_id"],
            "candidate_action": candidate["action"],
            "failure_run_seconds": failure_run_seconds,
            "result": result,
            "repeat_index": repeat_index,
            "llm_generation_seconds": (
                llm_generation_seconds
                if method in {
                    "llm_direct_isolated",
                    "llm_validated",
                }
                else None
            ),
            "rule_planning_seconds": (
                rule_planning_seconds
                if method == "rule_based_gated"
                else None
            ),
        })

        progress(
            f"  METHOD COMPLETE | {method} | status={result.get('status')} | "
            f"duration={result.get('method_duration_seconds', 'n/a')}s"
        )

    # Attach the same RCA evaluation to each method's result.
    for row in rows:
        row["expected_root_cause_code"] = expected_root_cause
        row["predicted_root_cause_code"] = predicted_root_cause
        row["diagnosis_correct"] = diagnosis_correct
        row["repeat_index"] = repeat_index

    # Save results after adding the diagnosis fields.
    progress("STEP 6/6 | Saving trial-level results for this case.")
    for row in rows:
        append_jsonl(CURRENT_RUN_PATH, row)

    case_duration = perf_counter() - case_started
    progress(
        f"CASE COMPLETE | {case['case_id']} | rows_saved={len(rows)} | "
        f"elapsed={case_duration:.3f}s"
    )
    if stop_after_case:
        progress(
            "RUN WILL STOP AFTER THIS CASE to prevent repeated requests against "
            "an exhausted or delayed provider quota.",
            "WARNING",
        )

    return rows


def summarize(rows):
    methods = sorted({
        row["method"] for row in rows
    })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len({row["case_id"] for row in rows}),
        "trial_records": len(rows),
        "methods": {},
        "interpretation_note": (
            "Overall recovery rate uses all recorded method rows as its denominator. "
            "Conditional automatic recovery excludes human-review cases and recorded "
            "operational/generation failures. Scenario repeats are repeated observations "
            "of fixed project-authored templates, not independent real-world incidents."
        ),
    }

    diagnosis_by_case = {}

    for row in rows:
        expected = row.get("expected_root_cause_code")
        predicted = row.get("predicted_root_cause_code")

        if expected is None or predicted is None:
            continue

        key = (
            row["case_id"],
            row.get("repeat_index", 0)
        )

        diagnosis_by_case[key] = {
            "expected": expected,
            "predicted": predicted
        }

    diagnosis_results = list(diagnosis_by_case.values())

    diagnosis_accuracy = (
        sum(
            item["expected"] == item["predicted"]
            for item in diagnosis_results
        ) / len(diagnosis_results)
        if diagnosis_results else None
    )

    output["diagnosis_evaluation"] = {
        "evaluated_cases": len(diagnosis_results),
        "correct": sum(
            item["expected"] == item["predicted"]
            for item in diagnosis_results
        ),
        "accuracy": diagnosis_accuracy
    }

    for method in methods:
        group = [
            row for row in rows
            if row["method"] == method
        ]

        total = len(group)

        recovered = sum(
            row["result"].get("status") == "recovered"
            for row in group
        )

        escalated = sum(
            row["result"].get("status")
            == "needs_human_approval"
            for row in group
        )

        statuses = [
            str((row.get("result") or {}).get("status", "missing_status"))
            for row in group
        ]
        status_counts = {
            status: statuses.count(status)
            for status in sorted(set(statuses))
        }
        operational_failure_statuses = {
            "candidate_generation_failed",
            "provider_quota_exhausted",
            "provider_rate_limit_deferred",
            "provider_request_failed",
            "case_execution_error",
        }
        operational_failures = sum(
            status in operational_failure_statuses for status in statuses
        )
        provider_rate_limit_failures = sum(
            status in {"provider_quota_exhausted", "provider_rate_limit_deferred"}
            for status in statuses
        )

        # Human-review cases and attempts with no usable candidate are reported
        # separately rather than being treated as evaluated automatic repairs.
        eligible = [
            row for row in group
            if (row.get("result") or {}).get("status") != "needs_human_approval"
            and (row.get("result") or {}).get("status") not in operational_failure_statuses
        ]

        auto_recovered = sum(
            (row.get("result") or {}).get("status") == "recovered"
            for row in eligible
        )

        validation_statuses = [
            row["result"].get("validation_status")
            for row in group
            if row["result"].get("validation_status")
            not in (None, "not_run", "needs_human_approval")
        ]

        validation_passes = sum(
            status == "passed"
            for status in validation_statuses
        )

        durations = [
            row["result"].get("method_duration_seconds")
            for row in group
            if row["result"].get("method_duration_seconds")
            is not None
        ]

        per_failure = {}

        for failure_type in sorted({
            row["failure_type"] for row in group
        }):
            items = [
                row for row in group
                if row["failure_type"] == failure_type
            ]

            item_statuses = [
                str((item.get("result") or {}).get("status", "missing_status"))
                for item in items
            ]
            per_failure[failure_type] = {
                "cases": len(items),
                "recovered": item_statuses.count("recovered"),
                "human_review_required": item_statuses.count("needs_human_approval"),
                "operational_failures": sum(
                    status in operational_failure_statuses for status in item_statuses
                ),
                "status_counts": {
                    status: item_statuses.count(status)
                    for status in sorted(set(item_statuses))
                },
            }

        output["methods"][method] = {
            "cases": total,
            "recovered": recovered,
            "overall_recovery_rate": recovered / total if total else None,
            "end_to_end_recovery_rate": recovered / total if total else None,
            "automatically_eligible_cases": len(eligible),
            "automatic_recovery_rate": (
                auto_recovered / len(eligible) if eligible else None
            ),
            "human_review_required": escalated,
            "candidate_generation_failed": status_counts.get("candidate_generation_failed", 0),
            "provider_rate_limit_failures": provider_rate_limit_failures,
            "operational_failure_cases": operational_failures,
            "status_counts": status_counts,
            "validation_attempts": len(validation_statuses),
            "validation_pass_rate": (
                validation_passes / len(validation_statuses)
                if validation_statuses else None
            ),
            "mean_method_duration_seconds": (
                sum(durations) / len(durations) if durations else None
            ),
            "per_failure_type": per_failure,
        }

    
    # Measure LLM generation and combined generation/repair latency.
    for method in (
        "llm_direct_isolated",
        "llm_validated",
    ):
        group = [
            row for row in rows
            if row.get("method") == method
        ]

        generation_times = [
            float(row["llm_generation_seconds"])
            for row in group
            if row.get("llm_generation_seconds") is not None
        ]

        combined_times = []

        for row in group:
            generation_time = row.get(
                "llm_generation_seconds"
            )
            result = row.get("result", {})
            method_time = result.get(
                "method_duration_seconds"
            )

            if (
                generation_time is not None
                and method_time is not None
                and result.get("status") not in {
                    "candidate_generation_failed",
                    "provider_quota_exhausted",
                    "provider_rate_limit_deferred",
                    "provider_request_failed",
                    "case_execution_error",
                }
            ):
                combined_times.append(
                    float(generation_time) + float(method_time)
                )

        if method in output["methods"]:
            output["methods"][method][
                "mean_llm_generation_seconds"
            ] = (
                round(
                    sum(generation_times)
                    / len(generation_times),
                    6
                )
                if generation_times else None
            )

            output["methods"][method][
                "mean_generation_plus_method_seconds"
            ] = (
                round(sum(combined_times) / len(combined_times), 6)
                if combined_times else None
            )
            output["methods"][method]["generation_timed_cases"] = len(generation_times)
            output["methods"][method]["generation_plus_method_timed_cases"] = len(combined_times)
            successful_generation_times = [
                float(row["llm_generation_seconds"])
                for row in group
                if row.get("llm_generation_seconds") is not None
                and row.get("candidate_id") is not None
            ]
            output["methods"][method]["mean_generation_seconds_for_valid_candidates"] = (
                round(sum(successful_generation_times) / len(successful_generation_times), 6)
                if successful_generation_times else None
            )
            output["methods"][method]["valid_candidate_generation_timed_cases"] = len(
                successful_generation_times
            )

    # Measure rule-based planning + repair execution.
    rule_group = [
        row for row in rows
        if row.get("method") == "rule_based_gated"
    ]

    planning_times = [
        float(row["rule_planning_seconds"])
        for row in rule_group
        if row.get("rule_planning_seconds") is not None
    ]

    combined_times = []

    for row in rule_group:
        planning_time = row.get("rule_planning_seconds")
        method_time = row.get("result", {}).get(
            "method_duration_seconds"
        )

        if planning_time is not None and method_time is not None:
            combined_times.append(
                float(planning_time) + float(method_time)
            )

    if "rule_based_gated" in output["methods"]:
        output["methods"]["rule_based_gated"][
            "mean_repair_planning_seconds"
        ] = (
            round(sum(planning_times) / len(planning_times), 6)
            if planning_times else None
        )

        output["methods"]["rule_based_gated"][
            "mean_planning_plus_method_seconds"
        ] = (
            round(sum(combined_times) / len(combined_times), 6)
            if combined_times else None
        )

    return output


CURRENT_RUN_PATH = None


def _resolve_project_path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _prepare_capture_path():
    """Require a fresh capture file so logs cannot silently mix runs."""
    raw = os.getenv("SHMLP_LLM_IO_LOG_PATH", "").strip()
    if not raw:
        raise RuntimeError(
            "LLM request capture is required for research runs. Set "
            "SHMLP_LLM_IO_LOG_PATH to a new, run-specific JSONL path."
        )

    path = _resolve_project_path(raw)
    if path.exists() and path.stat().st_size > 0:
        raise RuntimeError(
            f"Capture file already contains data: {path}. Choose a fresh path; "
            "existing evidence must not be appended to or overwritten."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(fd)
    try:
        path.chmod(0o600)
    except OSError:
        pass

    # llm_io_capture resolves relative paths against process cwd; store an absolute
    # path after changing cwd to the project root so its write target is unambiguous.
    os.environ["SHMLP_LLM_IO_LOG_PATH"] = str(path)
    return path


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _audit_capture_log(path: Path) -> dict:
    """Summarize capture integrity without copying prompts or model responses."""
    from collections import Counter
    from datetime import datetime

    statuses = Counter()
    malformed = 0
    rate_limit_failures = 0
    timestamps = []
    total = 0

    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            total += 1
            status = str(record.get("status", "missing_status"))
            statuses[status] += 1
            if status == "request_failed":
                error = record.get("error") or {}
                text = " ".join((str(error.get("type", "")), str(error.get("message_redacted", "")))).lower() if isinstance(error, dict) else str(error).lower()
                if any(marker in text for marker in ("429", "rate limit", "ratelimit", "tokens per minute", "tokens per day", "requests per day", "tpm", "tpd", "rpd")):
                    rate_limit_failures += 1
            try:
                raw_timestamp = str(record.get("timestamp_utc", ""))
                if raw_timestamp:
                    timestamps.append(datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")))
            except (TypeError, ValueError):
                pass

    return {
        "capture_filename": path.name,
        "records": total,
        "malformed_jsonl_lines": malformed,
        "status_counts": dict(sorted(statuses.items())),
        "rate_limit_failed_interactions": rate_limit_failures,
        "first_interaction_utc": min(timestamps).isoformat() if timestamps else None,
        "last_interaction_utc": max(timestamps).isoformat() if timestamps else None,
    }


def _record_case_execution_error(case, repeat_index, exc):
    """Preserve three method rows for a scenario that failed before evaluation."""
    message = safe_error_summary(exc)
    failed_rows = []
    for method in ("rule_based_gated", "llm_direct_isolated", "llm_validated"):
        row = {
            "case_id": case["case_id"],
            "incident_id": None,
            "failure_type": case["failure_type"],
            "method": method,
            "repeat_index": repeat_index,
            "result": {
                "status": "case_execution_error",
                "failure_kind": "benchmark_execution",
                "error": message,
            },
        }
        append_jsonl(CURRENT_RUN_PATH, row)
        failed_rows.append(row)
    return failed_rows


def main():
    global CURRENT_RUN_PATH

    parser = argparse.ArgumentParser(
        description=(
            "Run the live three-path self-healing benchmark with stage-by-stage "
            "progress, fresh capture logs, and quota-aware stopping."
        )
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="Number of repeats per selected scenario (default: 1).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help=(
            "Directory for this run's raw results, summary, and manifest. "
            "Relative paths are resolved from the project root."
        ),
    )
    parser.add_argument(
        "--case-ids", nargs="+", default=None,
        help="Optional subset of case IDs for a smoke/pilot run; list exact IDs.",
    )
    parser.add_argument(
        "--max-rate-limit-attempts", type=int, default=4,
        help="Maximum attempts for temporary HTTP 429s (default: 4).",
    )
    parser.add_argument(
        "--max-rate-limit-wait-seconds", type=float, default=30.0,
        help=(
            "Do not sleep on temporary rate limits for longer than this; "
            "save a partial run and stop instead (default: 30 seconds)."
        ),
    )
    parser.add_argument(
        "--preflight-only", action="store_true",
        help="Validate SDK/config/capture setup and write a manifest without calling the API.",
    )
    args = parser.parse_args()

    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.max_rate_limit_attempts < 1:
        parser.error("--max-rate-limit-attempts must be at least 1")
    if args.max_rate_limit_wait_seconds < 0:
        parser.error("--max-rate-limit-wait-seconds cannot be negative")

    os.chdir(ROOT)
    load_dotenv(ROOT / ".env", override=False)

    all_cases = read_cases()
    if args.case_ids:
        wanted = set(args.case_ids)
        known = {case["case_id"] for case in all_cases}
        unknown = sorted(wanted - known)
        if unknown:
            parser.error("Unknown case ID(s): " + ", ".join(unknown))
        cases = [case for case in all_cases if case["case_id"] in wanted]
    else:
        cases = all_cases

    if not cases:
        parser.error("No scenarios were selected.")

    output_dir = _resolve_project_path(args.output_dir) if args.output_dir else RESULT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    try:
        capture_path = _prepare_capture_path()
    except (OSError, RuntimeError) as exc:
        progress(f"PREFLIGHT FAILED | {exc}", "ERROR")
        progress(
            "No API request was sent. Set SHMLP_LLM_IO_LOG_PATH to a fresh path, "
            "then rerun the preflight.",
            "ERROR",
        )
        return 2

    CURRENT_RUN_PATH = output_dir / f"repeated_trials_{run_id}.jsonl"
    summary_path = output_dir / f"repeated_trials_summary_{run_id}.json"
    llm_manifest_path = output_dir / f"llm_run_manifest_{run_id}.json"

    llm_manifest = write_manifest(llm_manifest_path, root=ROOT)
    llm_manifest["benchmark_settings"] = {
        "runner": "benchmarks.repeated_trials",
        "run_id": run_id,
        "repeats_requested": args.repeats,
        "scenario_count": len(cases),
        "selected_case_ids": [case["case_id"] for case in cases],
        "expected_trial_records": len(cases) * args.repeats * 3,
        "max_rate_limit_attempts": args.max_rate_limit_attempts,
        "max_rate_limit_wait_seconds": args.max_rate_limit_wait_seconds,
        "capture_filename": capture_path.name,
        "raw_result_filename": CURRENT_RUN_PATH.name,
        "summary_filename": summary_path.name,
    }
    _write_json(llm_manifest_path, llm_manifest)

    if llm_manifest.get("status") != "ready_to_attempt_live_run":
        progress(
            "PREFLIGHT FAILED | missing/incompatible configuration: "
            + ", ".join(llm_manifest.get("missing_items", [])),
            "ERROR",
        )
        progress(f"Manifest: {llm_manifest_path}", "ERROR")
        return 2
    if not llm_manifest.get("llm_io_capture_enabled"):
        progress("PREFLIGHT FAILED | capture is not enabled in manifest.", "ERROR")
        return 2

    progress("PREFLIGHT PASSED | SDK pin and provider configuration are present.")
    progress(f"RUN ID | {run_id}")
    progress(f"MODEL | {llm_manifest.get('model_identifier')}")
    progress(f"ENDPOINT | {llm_manifest.get('endpoint_sanitized')}")
    progress(f"CAPTURE | {capture_path}")
    progress(f"RAW RESULTS | {CURRENT_RUN_PATH}")
    progress(f"SUMMARY | {summary_path}")

    if args.preflight_only:
        progress("PREFLIGHT-ONLY mode: no benchmark cases or API requests executed.")
        return 0

    # Create the result stream before the first task so any later stop has a
    # durable, unambiguous run artifact.
    CURRENT_RUN_PATH.touch(exist_ok=False)
    planned_executions = len(cases) * args.repeats
    planned_rows = planned_executions * 3
    progress(
        "RUN START | pipeline fault injection -> incident -> RCA -> deterministic "
        "candidate -> LLM candidate -> direct/gated validation/recovery -> save results"
    )
    progress(
        f"PLAN | templates={len(cases)} | repeats={args.repeats} | "
        f"case executions={planned_executions} | expected method rows={planned_rows}"
    )
    progress(
        "POLICY | dependency modifications require human review; the LLM never "
        "authorizes arbitrary code, shell commands, or package installation."
    )

    rows = []
    completed_executions = 0
    stop_reason = None
    case_execution_errors = 0

    for repeat_index in range(args.repeats):
        for case in cases:
            position = completed_executions + 1
            try:
                case_rows = evaluate_case(
                    case,
                    repeat_index,
                    case_position=position,
                    planned_case_executions=planned_executions,
                    planned_repeats=args.repeats,
                    max_rate_limit_attempts=args.max_rate_limit_attempts,
                    max_rate_limit_wait_seconds=args.max_rate_limit_wait_seconds,
                )
            except Exception as exc:
                case_execution_errors += 1
                progress(
                    f"CASE FAILED | {case['case_id']} | repeat={repeat_index + 1} | "
                    f"{safe_error_summary(exc)}. Recording explicit failure rows.",
                    "ERROR",
                )
                case_rows = _record_case_execution_error(case, repeat_index, exc)

            rows.extend(case_rows)
            completed_executions += 1

            statuses = {
                (row.get("result") or {}).get("status") for row in case_rows
            }
            if "provider_quota_exhausted" in statuses:
                stop_reason = "provider_daily_quota_exhausted"
                break
            if "provider_rate_limit_deferred" in statuses:
                stop_reason = "provider_rate_limit_deferred"
                break
        if stop_reason:
            break

    summary = summarize(rows)
    completed = completed_executions == planned_executions and stop_reason is None
    if completed and case_execution_errors == 0:
        run_status = "completed"
    elif stop_reason == "provider_daily_quota_exhausted":
        run_status = "stopped_provider_quota"
    elif stop_reason == "provider_rate_limit_deferred":
        run_status = "stopped_rate_limit_wait"
    else:
        run_status = "completed_with_case_errors" if completed else "incomplete"

    summary["run_metadata"] = {
        "run_id": run_id,
        "run_status": run_status,
        "stop_reason": stop_reason,
        "repeats_requested": args.repeats,
        "scenario_templates_requested": len(cases),
        "planned_case_executions": planned_executions,
        "completed_case_executions": completed_executions,
        "planned_trial_records": planned_rows,
        "written_trial_records": len(rows),
        "completion_fraction": (
            completed_executions / planned_executions if planned_executions else None
        ),
        "case_execution_errors": case_execution_errors,
        "capture_filename": capture_path.name,
        "raw_results_filename": CURRENT_RUN_PATH.name,
        "manifest_filename": llm_manifest_path.name,
    }
    summary["llm_run_manifest"] = llm_manifest_path.name
    summary["run_metadata"]["capture_audit"] = _audit_capture_log(capture_path)
    _write_json(summary_path, summary)

    progress("RUN SUMMARY | " + json.dumps(summary["run_metadata"], sort_keys=True))
    for method, metrics in summary.get("methods", {}).items():
        progress(
            f"METHOD SUMMARY | {method} | recovered={metrics.get('recovered')}/"
            f"{metrics.get('cases')} | overall={metrics.get('overall_recovery_rate')} | "
            f"eligible={metrics.get('automatically_eligible_cases')} | "
            f"conditional_automatic_recovery={metrics.get('automatic_recovery_rate')} | "
            f"human_review={metrics.get('human_review_required')} | "
            f"provider_rate_limit_failures={metrics.get('provider_rate_limit_failures')}"
        )
    progress(f"RAW RESULTS SAVED | {CURRENT_RUN_PATH}")
    progress(f"SUMMARY SAVED | {summary_path}")
    progress(f"MANIFEST SAVED | {llm_manifest_path}")
    progress(f"CAPTURE SAVED | {capture_path}")

    if stop_reason:
        progress(
            f"RUN INCOMPLETE | {stop_reason}. Existing rows and summary have been saved; "
            "no more LLM requests were issued after the stop condition.",
            "ERROR",
        )
        return 3
    if case_execution_errors:
        progress("RUN COMPLETED WITH CASE-LEVEL ERRORS; inspect raw rows before analysis.", "WARNING")
        return 1

    progress("RUN COMPLETED | all planned case executions produced three method rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
