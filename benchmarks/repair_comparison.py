
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from healing.incidents.incident_store import IncidentStore
from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.repair.repair_policy import enforce_repair_policy
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine

from benchmarks.direct_llm_baseline import DirectLLMBaseline


INCIDENT_PATH = "artifacts/incidents/incidents.jsonl"
LLM_CANDIDATE_PATH = (
    "artifacts/incidents/llm_repair_candidates.jsonl"
)
RESULT_DIR = Path("benchmarks/results")
VALIDATION_PATH = (
    "artifacts/incidents/comparison_validation.jsonl"
)
RECOVERY_PATH = (
    "artifacts/incidents/comparison_recovery.jsonl"
)

FAILURE_TYPES = [
    "schema_change",
    "data_quality",
    "configuration_error",
    "dependency_error",
]


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def append_jsonl(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


from time import perf_counter


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
            VALIDATION_PATH
        )

        validation_status = validation.get(
            "status", "unknown"
        )

        if validation_status != "passed":
            result = {
                "status": validation_status,
                "validation_status": validation_status,
                "validation_seconds": validation.get(
                    "duration_seconds"
                ),
            }

        elif candidate.get(
            "requires_human_approval", False
        ):
            result = {
                "status": "needs_human_approval",
                "validation_status": "passed",
                "validation_seconds": validation.get(
                    "duration_seconds"
                ),
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
                RECOVERY_PATH
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
                "error": recovery.get("error"),
            }

    except Exception as exc:
        result = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    result["method_duration_seconds"] = round(
        perf_counter() - started, 6
    )

    return result


def summarize(rows):
    methods = sorted({
        row["method"] for row in rows
    })

    summary = {}

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

        # Exclude human-review cases from the automatically
        # recoverable subset.
        eligible = [
            row for row in group
            if row["result"].get("status")
            != "needs_human_approval"
        ]

        eligible_recovered = sum(
            row["result"].get("status") == "recovered"
            for row in eligible
        )

        # A real validation attempt has a resulting status.
        # Human-review routing is not a normal failed validation.
        validation_attempts = [
            row["result"].get("validation_status")
            for row in group
            if row["result"].get("validation_status")
            not in (None, "needs_human_approval", "not_run")
        ]

        validation_passes = sum(
            status == "passed"
            for status in validation_attempts
        )

        durations = [
            row["result"].get(
                "method_duration_seconds",
                row["result"].get("duration_seconds")
            )
            for row in group
        ]

        durations = [
            value for value in durations
            if value is not None
        ]

        summary[method] = {
            "total_scenarios": total,

            "overall_recovery_rate": (
                recovered / total if total else None
            ),

            "automatically_recoverable_scenarios": len(eligible),

            "automatic_recovery_rate": (
                eligible_recovered / len(eligible)
                if eligible else None
            ),

            "human_review_required": escalated,

            "validation_attempts": len(validation_attempts),

            "validation_pass_rate": (
                validation_passes / len(validation_attempts)
                if validation_attempts else None
            ),

            "mean_method_duration_seconds": (
                sum(durations) / len(durations)
                if durations else None
            ),
        }

    return summary


def main():
    incidents = IncidentStore(
        INCIDENT_PATH
    ).get_all()

    incident_map = {
        incident.incident_id: incident
        for incident in incidents
    }

    candidates = read_jsonl(LLM_CANDIDATE_PATH)

    # Keep the latest saved LLM candidate for each failure type.
    latest = {}

    for candidate in candidates:
        failure_type = candidate.get("failure_type")
        if failure_type in FAILURE_TYPES:
            latest[failure_type] = candidate

    missing = set(FAILURE_TYPES) - set(latest)

    if missing:
        raise RuntimeError(
            "Missing LLM candidates for: "
            + ", ".join(sorted(missing))
        )

    rows = []

    for failure_type in FAILURE_TYPES:
        llm_candidate = latest[failure_type]

        incident = incident_map.get(
            llm_candidate["incident_id"]
        )

        if incident is None:
            print(
                f"Skipping {failure_type}: matching incident "
                "was not found."
            )
            continue

        if incident.failure_type != failure_type:
            raise ValueError(
                f"Incident type mismatch for {failure_type}."
            )

        print(f"\nEvaluating {failure_type}")

        # Generate deterministic repair for the same incident.
        rca = RuleBasedRCA().analyze(incident)

        rule_candidate = (
            RepairGenerator().generate(
                incident, rca
            ).to_dict()
        )

        rule_candidate = enforce_repair_policy(
            rule_candidate
        )

        llm_candidate = enforce_repair_policy(
            llm_candidate
        )

        # A. Rule-based candidate + validation gate.
        rows.append({
            "incident_id": incident.incident_id,
            "failure_type": failure_type,
            "method": "rule_based_gated",
            "result": run_gated(
                rule_candidate, incident
            ),
        })

        # B. LLM candidate without the separate preflight gate.
        # Execution remains isolated and uses allowlisted actions.
        direct_result = DirectLLMBaseline().run(
            llm_candidate,
            incident
        )

        rows.append({
            "incident_id": incident.incident_id,
            "failure_type": failure_type,
            "method": "llm_direct_isolated",
            "result": direct_result,
        })

        # C. Same LLM candidate with sandbox validation.
        rows.append({
            "incident_id": incident.incident_id,
            "failure_type": failure_type,
            "method": "llm_validated",
            "result": run_gated(
                llm_candidate, incident
            ),
        })

    if not rows:
        raise RuntimeError(
            "No experiments were completed."
        )

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    raw_path = RESULT_DIR / f"comparison_{stamp}.jsonl"
    summary_path = RESULT_DIR / f"comparison_summary_{stamp}.json"

    for row in rows:
        append_jsonl(raw_path, row)

    summary = summarize(rows)

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\nCOMPARISON SUMMARY")
    print(json.dumps(summary, indent=2))

    print(f"\nDetailed results: {raw_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
