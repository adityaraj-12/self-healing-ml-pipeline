import argparse
import json
import logging
from pathlib import Path

import joblib
import yaml

from healing.monitor.pipeline_monitor import PipelineMonitor
from healing.detector.failure_detector import FailureDetector

from healing.incidents.context_builder import ContextBuilder
from healing.incidents.incident_builder import IncidentBuilder
from healing.incidents.incident_store import IncidentStore

from healing.rca.rca_service import RCAService
from healing.incidents.rca_store import RCAStore

from failures.injector import inject_failure
from pipeline.ingestion import load_data
from pipeline.preprocessing import split_data
from pipeline.training import train_model
from pipeline.evaluation import evaluate_model
from pipeline.schema_validation import (
    save_schema,
    validate_schema
)

from copy import deepcopy

from dotenv import load_dotenv

load_dotenv()

def load_trial_case(case_id, failure_type):
    if not case_id:
        return None

    with open(
        "benchmarks/scenarios/trial_cases.yaml",
        "r"
    ) as f:
        scenario_config = yaml.safe_load(f)

    matches = [
        case for case in scenario_config["cases"]
        if case["case_id"] == case_id
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected one scenario named {case_id!r}, "
            f"found {len(matches)}."
        )

    case = matches[0]

    if case["failure_type"] != failure_type:
        raise ValueError(
            f"Scenario {case_id!r} belongs to "
            f"{case['failure_type']!r}, not {failure_type!r}."
        )

    return case

def load_config():
    with open("configs/pipeline.yaml", "r") as f:
        return yaml.safe_load(f)


def load_failure_config():
    with open("configs/failures.yaml", "r") as f:
        return yaml.safe_load(f)


def setup_logging(log_path):
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True
    )


def save_metrics(metrics, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)


def run_pipeline(failure_type=None, case_id=None, repeat_index=0, auto_heal=False,):
    config = load_config()

    # Preserve the original healthy configuration.
    baseline_config = deepcopy(config)

    failure_config = load_failure_config()

    failure_case_id = case_id
    failure_parameters = {}
    # Unexpected runtime errors can occur without an explicitly injected
    # failure type. Keep incident context construction valid in that case.
    selected_case = None
    failure_ground_truth = {}

    if failure_type:
        active = dict(
            failure_config["failures"][failure_type]
        )

        selected_case = load_trial_case(
            case_id,
            failure_type
        )

        failure_ground_truth = (
            selected_case.get("ground_truth", {})
            if selected_case else {}
        )

        if selected_case:
            active.update(
                selected_case["parameters"]
            )

        # Override only this failure type.
        failure_config["failures"][failure_type] = active

        failure_parameters = {
            key: value
            for key, value in active.items()
            if key != "enabled"
        }

    if (
        failure_type == "data_quality"
        and selected_case is not None
    ):
        base_seed = int(
            selected_case["parameters"].get(
                "random_seed", 42
            )
        )

        active["random_seed"] = (
            base_seed + repeat_index
        )

    setup_logging(config["artifacts"]["log"])

    monitor = PipelineMonitor()
    monitor.start()

    detector = FailureDetector()
    context_builder = ContextBuilder()
    incident_builder = IncidentBuilder()

    incident_store = IncidentStore(
        config["artifacts"]["incidents"]
    )

    logging.info("PIPELINE_START")
    logging.info(
        "FAILURE_TYPE=%s",
        failure_type
    )

    try:
        monitor.set_stage("data_loading")
        logging.info("Loading dataset")

        x, y = load_data()

        logging.info(
            "Dataset loaded: rows=%d columns=%d",
            x.shape[0],
            x.shape[1]
        )

        # --------------------------------------------------
        # Failure injection
        # --------------------------------------------------
        monitor.set_stage("failure_injection")
        if failure_type:
            
            logging.warning(
                "FAILURE_INJECTION_START type=%s",
                failure_type
            )

            x, config = inject_failure(
                failure_type,
                x,
                {
                    **config,
                    "failures": failure_config["failures"]
                }
            )

            logging.warning(
                "FAILURE_INJECTION_COMPLETE type=%s config=%s",
                failure_type,
                config["model"]
            )

        # --------------------------------------------------
        # Schema validation
        # --------------------------------------------------

        schema_path = config["artifacts"]["schema"]
        monitor.set_stage("schema_validation")

        if failure_type == "schema_change":
            validate_schema(x, schema_path)

        elif not Path(schema_path).exists():
            save_schema(x, schema_path)

        # --------------------------------------------------
        # Split
        # --------------------------------------------------

        monitor.set_stage("data_split")
        logging.info("Splitting dataset")

        x_train, x_test, y_train, y_test = split_data(
            x,
            y,
            test_size=config["split"]["test_size"],
            random_state=config["split"]["random_state"]
        )

        # --------------------------------------------------
        # Training
        # --------------------------------------------------

        monitor.set_stage("training")
        logging.info(
            "Training model with config=%s",
            config["model"]
        )

        model = train_model(
            x_train,
            y_train,
            C=config["model"]["C"],
            max_iter=config["model"]["max_iter"]
        )

        # --------------------------------------------------
        # Evaluation
        # --------------------------------------------------

        monitor.set_stage("evaluation")
        logging.info("Evaluating model")

        metrics = evaluate_model(
            model,
            x_test,
            y_test
        )

        save_metrics(
            metrics,
            config["artifacts"]["metrics"]
        )

        model_path = Path(config["artifacts"]["model"])
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_path)

        logging.info(
            "PIPELINE_SUCCESS metrics=%s",
            metrics
        )

        print("\nPipeline completed successfully.")
        print("\nMetrics:")

        for key, value in metrics.items():
            print(f"{key}: {value:.4f}")

    except Exception as e:

        monitor_state = monitor.failure()

        logging.exception(
            "PIPELINE_FAILED"
        )

        # --------------------------------------------
        # Build structured runtime context
        # --------------------------------------------

        context = context_builder.build(
            exception=e,
            monitor_state=monitor_state,
            config=config,
            failure_type=failure_type,
            baseline_config=baseline_config,
            failure_case_id=failure_case_id,
            failure_parameters=failure_parameters,
            ground_truth=failure_ground_truth,
            repeat_index=repeat_index
        )

        # --------------------------------------------
        # Automatically detect failure type
        # --------------------------------------------

        detection = detector.detect(
            exception=e,
            context=context
        )

        logging.warning(
            "FAILURE_DETECTED type=%s confidence=%.2f",
            detection["failure_type"],
            detection["confidence"]
        )

        # --------------------------------------------
        # Create incident
        # --------------------------------------------

        incident = incident_builder.build(
            detection=detection,
            exception=e,
            stage=monitor_state[
                "current_stage"
            ],
            config=config,
            context=context
        )

        # --------------------------------------------
        # Save incident
        # --------------------------------------------

        incident_store.save(
            incident
        )

        print("\nPipeline failed.")

        print(
            f"Detected failure: "
            f"{incident.failure_type}"
        )

        print(
            f"Confidence: "
            f"{incident.confidence:.2f}"
        )

        print(
            f"Stage: "
            f"{incident.stage}"
        )

        print(
            f"Error: "
            f"{incident.exception_type}: "
            f"{incident.error_message}"
        )

        print(
            f"Incident ID: "
            f"{incident.incident_id}"
        )

        # --------------------------------------------
        # Root Cause Analysis
        # --------------------------------------------

        rca_service = RCAService()

        rca_result = rca_service.analyze_rule_based(
            incident
        )

        rca_store = RCAStore(
            config["artifacts"]["rca"]
        )

        rca_store.save(
            rca_result
        )

        logging.warning(
            "RCA_COMPLETE method=%s "
            "root_cause=%s "
            "confidence=%.2f",
            rca_result.method,
            rca_result.root_cause,
            rca_result.confidence
        )

        print("\nRoot Cause Analysis:")
        print(
            f"Root cause: "
            f"{rca_result.root_cause}"
        )

        print(
            f"Repair target: "
            f"{rca_result.repair_target}"
        )

        print(
            f"Suggested action: "
            f"{rca_result.suggested_action}"
        )

        print(
            f"RCA confidence: "
            f"{rca_result.confidence:.2f}"
        )

        
        if auto_heal:
            from healing.orchestrator import HealingOrchestrator

            print("\nStarting automated healing workflow...")

            try:
                healing_result = HealingOrchestrator().run(
                    incident,
                    rca_result=rca_result,
                )
            except Exception as healing_exc:
                logging.exception("HEALING_ORCHESTRATION_FAILED")
                healing_result = {
                    "incident_id": incident.incident_id,
                    "status": "failed",
                    "error": (
                        f"{type(healing_exc).__name__}: "
                        f"{healing_exc}"
                    ),
                }

            print("\nHealing orchestration result:")
            print(json.dumps(healing_result, indent=2, default=str))

            return healing_result

        raise



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--failure",
        choices=[
            "schema_change",
            "data_quality",
            "configuration_error",
            "dependency_error"
        ],
        default=None
    )
    parser.add_argument(
        "--case-id",
        default=None,
        help="Run a specific controlled failure scenario."
    )
    parser.add_argument(
        "--repeat-index",
        type=int,
        default=0
    )
    parser.add_argument(
        "--auto-heal",
        action="store_true",
        help="Attempt policy-controlled healing after a pipeline failure.",
    )

    args = parser.parse_args()

    run_pipeline(
        failure_type=args.failure,
        case_id=args.case_id,
        repeat_index=args.repeat_index,
        auto_heal=args.auto_heal,
    )