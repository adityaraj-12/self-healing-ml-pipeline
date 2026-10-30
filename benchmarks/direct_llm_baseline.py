
import numpy as np
import yaml

from failures.injector import inject_failure
from pipeline.ingestion import load_data
from pipeline.preprocessing import split_data
from pipeline.training import train_model
from pipeline.evaluation import evaluate_model
from pipeline.schema_validation import validate_schema
from healing.recovery.repair_executor import RepairExecutor

from time import perf_counter


class DirectLLMBaseline:

    def __init__(self):
        self.executor = RepairExecutor()

        with open("configs/pipeline.yaml", "r") as f:
            self.pipeline_config = yaml.safe_load(f)

        with open("configs/failures.yaml", "r") as f:
            self.failure_config = yaml.safe_load(f)

    def run(self, candidate, incident=None):
        started = perf_counter()

        failure_type = candidate["failure_type"]

        # Create a fresh configuration for every experiment.
        config = {
            **self.pipeline_config,
            "model": dict(self.pipeline_config["model"]),
            "split": dict(self.pipeline_config["split"]),
            "artifacts": dict(self.pipeline_config["artifacts"]),
            "failures": {
                name: dict(settings)
                for name, settings in self.failure_config["failures"].items()
            },
        }

        # Reuse the exact failure parameters from the incident.
        if incident is not None:
            injection = incident.context.get(
                "failure_injection", {}
            )

            parameters = injection.get("parameters", {})
            failure_type = incident.failure_type

            if failure_type in config["failures"]:
                config["failures"][failure_type] = {
                    **config["failures"][failure_type],
                    **parameters,
                }

        # Dependency changes must remain under human control.
        if failure_type == "dependency_error":
            return {
                "status": "needs_human_approval",
                "reason": "Dependency changes are not automatic.",
                "duration_seconds": round(
                    perf_counter() - started, 6
                ),
            }

        try:
            # Fresh in-memory data and configuration for every run.
            x, y = load_data()

            # Inject the same failure used by the other methods.
            x, config = inject_failure(
                failure_type, x, config
            )

            # Apply only predefined actions.
            if failure_type == "schema_change":
                x = self.executor.apply_schema_repair(
                    x, candidate
                )

                validate_schema(
                    x, config["artifacts"]["schema"]
                )

            elif failure_type == "configuration_error":
                config = self.executor.apply_configuration_repair(
                    config, candidate
                )

            # Split after injecting the failure, but before imputation.
            x_train, x_test, y_train, y_test = split_data(
                x,
                y,
                test_size=config["split"]["test_size"],
                random_state=config["split"]["random_state"],
            )

            if failure_type == "data_quality":
                x_train, x_test = (
                    self.executor.impute_training_test(
                        x_train, x_test, candidate
                    )
                )

            model = train_model(
                x_train,
                y_train,
                C=config["model"]["C"],
                max_iter=config["model"]["max_iter"],
            )

            metrics = evaluate_model(
                model, x_test, y_test
            )

            if not all(
                np.isfinite(value)
                for value in metrics.values()
            ):
                raise ValueError(
                    "Non-finite evaluation metric."
                )

            return {
                "status": "recovered",
                "metrics": metrics,
                "message": (
                    "Isolated repair execution and "
                    "post-execution checks succeeded."
                ),
                "duration_seconds": round(
                        perf_counter() - started, 6
                    ),
            }

        except Exception as exc:
            return {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "duration_seconds": round(
                        perf_counter() - started, 6
                    ),
            }
