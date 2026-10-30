from statistics import mean


def calculate_rate(numerator, denominator):
    if denominator == 0:
        return None

    return round(numerator / denominator, 4)


def summarize_results(records):
    total = len(records)

    detected = sum(
        record.get("detection_correct", False)
        for record in records
    )

    candidates = sum(
        record.get("candidate_generated", False)
        for record in records
    )

    validation_attempts = [
        record for record in records
        if record.get("validation_status") not in (
            None,
            "not_run"
        )
    ]

    validation_passed = sum(
        record.get("validation_status") == "passed"
        for record in validation_attempts
    )

    recovered = sum(
        record.get("recovery_status") == "recovered"
        for record in records
    )

    recovery_times = [
        record["recovery_duration_seconds"]
        for record in records
        if record.get("recovery_duration_seconds") is not None
    ]

    monitor_times = [
        record["monitor_elapsed_seconds"]
        for record in records
        if record.get("monitor_elapsed_seconds") is not None
    ]

    return {
        "total_scenarios": total,

        "failure_type_detection_accuracy": calculate_rate(
            detected, total
        ),

        "candidate_generation_rate": calculate_rate(
            candidates, total
        ),

        "validation_pass_rate": calculate_rate(
            validation_passed, len(validation_attempts)
        ),

        "end_to_end_recovery_rate": calculate_rate(
            recovered, total
        ),

        "human_review_required": sum(
            record.get("recovery_status")
            == "needs_human_approval"
            for record in records
        ),

        "mean_monitor_elapsed_seconds": (
            round(mean(monitor_times), 4)
            if monitor_times else None
        ),

        "mean_recovery_duration_seconds": (
            round(mean(recovery_times), 4)
            if recovery_times else None
        )
    }