class ContextBuilder:

    def build(
        self,
        exception,
        monitor_state,
        config,
        failure_type=None,
        baseline_config=None,
        failure_case_id=None,
        failure_parameters=None,
        ground_truth=None,
        repeat_index=0
    ):
        return {
            "runtime": monitor_state,

            "failure_injection": {
                "requested_type": failure_type,
                "case_id": failure_case_id,
                "repeat_index": repeat_index,
                "parameters": failure_parameters or {},
                "ground_truth": ground_truth or {}
            },

            "exception": {
                "type": type(exception).__name__,
                "message": str(exception)
            },

            "model": config.get("model", {}),

            # Preserve the known-good configuration
            # for comparison and repair planning.
            "baseline_config": baseline_config or {},

            "split": config.get("split", {})
        }