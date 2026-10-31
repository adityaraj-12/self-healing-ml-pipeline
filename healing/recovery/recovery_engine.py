import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import yaml

from failures.injector import inject_failure
from pipeline.ingestion import load_data
from pipeline.preprocessing import split_data
from pipeline.training import train_model
from pipeline.evaluation import evaluate_model
from pipeline.schema_validation import validate_schema

from healing.recovery.repair_executor import RepairExecutor
from copy import deepcopy

class RecoveryEngine:

    def __init__(self):
        self.executor = RepairExecutor()

        with open("configs/pipeline.yaml", "r") as f:
            self.pipeline_config = yaml.safe_load(f)

        with open("configs/failures.yaml", "r") as f:
            self.failure_config = yaml.safe_load(f)

    def assess_recovery_eligibility(
        self, incident, candidate, validation_report
    ):
        """Assess recovery eligibility without executing or modifying anything."""

        if candidate.get("incident_id") != incident.incident_id:
            return {
                "eligible": False,
                "status": "blocked",
                "reason": (
                    "Candidate incident_id does not match "
                    "the recovery incident."
                ),
            }

        if (
            validation_report.get("candidate_id")
            != candidate.get("candidate_id")
            or validation_report.get("incident_id")
            != incident.incident_id
            or validation_report.get("failure_type")
            != candidate.get("failure_type")
        ):
            return {
                "eligible": False,
                "status": "blocked",
                "reason": (
                    "Validation report does not match "
                    "the candidate and incident."
                ),
            }

        failure_type = incident.failure_type

        if candidate.get("failure_type") != failure_type:
            return {
                "eligible": False,
                "status": "blocked",
                "reason": "Failure type mismatch.",
            }

        if (
            validation_report.get("status") == "needs_human_approval"
            or candidate.get("requires_human_approval", False)
            or failure_type == "dependency_error"
        ):
            return {
                "eligible": False,
                "status": "needs_human_approval",
                "reason": (
                    "Human approval is required. "
                    "No repair has been applied."
                ),
            }

        if validation_report.get("status") != "passed":
            return {
                "eligible": False,
                "status": "blocked",
                "reason": (
                    "Candidate did not pass sandbox validation."
                ),
            }

        return {
            "eligible": True,
            "status": "eligible",
            "reason": "Candidate passed the recovery eligibility checks.",
        }

    def recover(self, incident, candidate, validation_report):
        start = perf_counter()

        result = {
            "incident_id": incident.incident_id,
            "candidate_id": candidate["candidate_id"],
            "failure_type": incident.failure_type,
            "started_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        eligibility = self.assess_recovery_eligibility(
            incident, candidate, validation_report
        )

        if not eligibility["eligible"]:
            result.update({
                "status": eligibility["status"],
                "reason": eligibility["reason"],
            })
            return self._finish(result, start)

        try:
            # --------------------------------------------
            # 2. Load clean data and configuration.
            # --------------------------------------------

            x, y = load_data()

            config = dict(self.pipeline_config)
            config["model"] = dict(
                self.pipeline_config["model"]
            )
            config["split"] = dict(
                self.pipeline_config["split"]
            )
            config["artifacts"] = dict(
                self.pipeline_config["artifacts"]
            )
            config["failures"] = deepcopy(
                self.failure_config["failures"]
            )

            injection = incident.context.get(
                "failure_injection", {}
            )

            parameters = injection.get("parameters", {})
            failure_type = incident.failure_type

            if failure_type in config["failures"]:
                config["failures"][failure_type] = {
                    **config["failures"][failure_type],
                    **parameters
                }

            # --------------------------------------------
            # 3. Reproduce the original failure.
            # --------------------------------------------

            x, config = inject_failure(
                failure_type,
                x,
                config
            )

            # --------------------------------------------
            # 4. Apply the candidate to this fresh copy.
            # --------------------------------------------

            if failure_type == "schema_change":
                x = self.executor.apply_schema_repair(
                    x, candidate
                )

                validate_schema(
                    x,
                    config["artifacts"]["schema"]
                )

            elif failure_type == "configuration_error":
                config = self.executor.apply_configuration_repair(
                    config, candidate
                )

            elif failure_type == "data_quality":
                pass  # Repair after the train/test split.

            else:
                raise ValueError(
                    f"Unsupported recovery type: {failure_type}"
                )

            # --------------------------------------------
            # 5. Prepare and, if necessary, repair data.
            # --------------------------------------------

            x_train, x_test, y_train, y_test = split_data(
                x,
                y,
                test_size=config["split"]["test_size"],
                random_state=config["split"]["random_state"]
            )

            if failure_type == "data_quality":
                x_train, x_test = (
                    self.executor.impute_training_test(
                        x_train,
                        x_test,
                        candidate
                    )
                )

            # --------------------------------------------
            # 6. Rerun the ML pipeline.
            # --------------------------------------------

            model = train_model(
                x_train,
                y_train,
                C=config["model"]["C"],
                max_iter=config["model"]["max_iter"]
            )

            metrics = evaluate_model(
                model,
                x_test,
                y_test
            )

            if not all(
                np.isfinite(value)
                for value in metrics.values()
            ):
                raise ValueError(
                    "Recovery produced non-finite metrics."
                )

            # --------------------------------------------
            # 7. Save versioned recovery artifacts.
            # Never overwrite the healthy baseline model.
            # --------------------------------------------

            output_dir = (
                Path("artifacts/recovered")
                / incident.incident_id
                / candidate["candidate_id"]
            )

            output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            model_path = output_dir / "model.joblib"
            metrics_path = output_dir / "metrics.json"

            joblib.dump(model, model_path)

            # --------------------------------------------
            # Verify the saved model can be reloaded.
            # --------------------------------------------

            loaded_model = joblib.load(model_path)

            pred_before_save = model.predict(x_test)
            pred_after_load = loaded_model.predict(x_test)

            predictions_identical = np.array_equal(
                pred_before_save,
                pred_after_load
            )

            reloaded_metrics = evaluate_model(
                loaded_model,
                x_test,
                y_test
            )

            metrics_identical = all(
                np.isclose(
                    metrics[key],
                    reloaded_metrics[key],
                    rtol=1e-9,
                    atol=1e-12
                )
                for key in metrics
            )

            post_recovery_check = {
                "model_reload_successful": True,
                "predictions_identical": bool(predictions_identical),
                "metrics_identical": bool(metrics_identical)
            }

            if not predictions_identical or not metrics_identical:
                raise ValueError(
                    "Post-recovery verification failed: "
                    f"{post_recovery_check}"
                )

            with metrics_path.open(
                "w", encoding="utf-8"
            ) as f:
                json.dump(metrics, f, indent=2)

            result.update({
                "status": "recovered",
                "metrics": metrics,
                "model_path": str(model_path),
                "metrics_path": str(metrics_path),
                "message": (
                    "Repair passed validation and the "
                    "recovered pipeline completed successfully."
                ),
                "post_recovery_check": post_recovery_check,
            })

        except Exception as exc:
            result.update({
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)
            })

        return self._finish(result, start)

    def _finish(self, result, start):
        result["duration_seconds"] = (
            perf_counter() - start
        )
        result["finished_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        return result

    def save_result(self, result, path):
        path = Path(path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")