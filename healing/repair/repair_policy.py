
from copy import deepcopy


ALLOWED_ACTIONS = {
    "schema_change": {"rename_column"},
    "data_quality": {"impute_missing_values"},
    "configuration_error": {"restore_configuration"},
    "dependency_error": {"verify_dependency"},
}


def enforce_repair_policy(candidate):
    candidate = deepcopy(candidate)

    failure_type = candidate.get("failure_type")
    action = candidate.get("action")

    allowed = ALLOWED_ACTIONS.get(failure_type, set())

    if action not in allowed:
        raise ValueError(
            f"Action {action!r} is not permitted "
            f"for failure type {failure_type!r}."
        )

    # Approval is determined by system policy, not the LLM.
    candidate["requires_human_approval"] = (
        failure_type == "dependency_error"
    )

    candidate["status"] = "proposed"

    return candidate
