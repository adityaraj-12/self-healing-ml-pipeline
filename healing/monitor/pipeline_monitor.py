from datetime import datetime, timezone
import time


class PipelineMonitor:

    def __init__(self):
        self.started_at = None
        self.current_stage = "initialization"
        self.start_time = None

    def start(self):
        self.started_at = datetime.now(
            timezone.utc
        ).isoformat()

        self.start_time = time.perf_counter()

        self.current_stage = "initialization"

    def set_stage(self, stage):
        self.current_stage = stage

    def get_state(self):
        elapsed = None

        if self.start_time is not None:
            elapsed = time.perf_counter() - self.start_time

        return {
            "started_at": self.started_at,
            "current_stage": self.current_stage,
            "elapsed_seconds": elapsed
        }

    def success(self):
        return {
            **self.get_state(),
            "status": "success"
        }

    def failure(self):
        return {
            **self.get_state(),
            "status": "failure"
        }