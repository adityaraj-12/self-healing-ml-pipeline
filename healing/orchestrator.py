from time import perf_counter

from healing.rca.rule_based_rca import RuleBasedRCA
from healing.repair.repair_generator import RepairGenerator
from healing.repair.repair_policy import enforce_repair_policy
from healing.validation.repair_validator import RepairValidator
from healing.recovery.recovery_engine import RecoveryEngine


class HealingOrchestrator:
    """
    Coordinates RCA, repair planning, policy enforcement,
    sandbox validation, and controlled recovery.

    Recovery execution is permitted only after validation passes.
    Dependency and other human-review cases never execute automatically.
    """

    def __init__(
        self,
        rca=None,
        repair_generator=None,
        validator=None,
        recovery_engine=None,
    ):
        self.rca = rca or RuleBasedRCA()
        self.repair_generator = repair_generator or RepairGenerator()
        self.validator = validator or RepairValidator()
        self.recovery_engine = recovery_engine or RecoveryEngine()

    def _result(
        self,
        incident,
        rca_result,
        candidate,
        validation_report,
        recovery_result,
        started,
    ):
        return {
            "incident_id": incident.incident_id,
            "status": recovery_result["status"],
            "rca": rca_result.to_dict(),
            "candidate": candidate,
            "validation_report": validation_report,
            "recovery_result": recovery_result,
            "duration_seconds": round(
                perf_counter() - started, 6
            ),
        }

    def run(self, incident, rca_result=None):
        started = perf_counter()

        if rca_result is None:
            rca_result = self.rca.analyze(incident)

        # Stage 1: Generate a proposed repair candidate.
        try:
            proposed = self.repair_generator.generate(
                incident, rca_result
            ).to_dict()
        except Exception as exc:
            failed = {
                "status": "candidate_generation_failed",
                "reason": f"{type(exc).__name__}: {exc}",
            }
            return self._result(
                incident, rca_result, None, failed, failed, started
            )

        # Stage 2: Enforce the system's repair policy.
        try:
            candidate = enforce_repair_policy(proposed)
        except Exception as exc:
            reason = (
                f"Repair policy rejected the proposed action: "
                f"{type(exc).__name__}: {exc}"
            )
            status = (
                "needs_human_approval"
                if proposed.get("requires_human_approval", False)
                else "blocked"
            )
            rejected = {
                "candidate_id": proposed.get("candidate_id"),
                "incident_id": incident.incident_id,
                "status": "rejected",
                "reason": reason,
            }
            blocked = {
                "status": status,
                "reason": reason,
            }
            return self._result(
                incident, rca_result, proposed, rejected,
                blocked, started
            )

        # Stage 3: Validate in an isolated workspace.
        try:
            validation_report = self.validator.validate(
                candidate, incident
            )
        except Exception as exc:
            validation_report = {
                "candidate_id": candidate["candidate_id"],
                "incident_id": incident.incident_id,
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
            }

        validation_status = validation_report.get("status")

        # A request for human review is not an ordinary repair failure.
        if (
            validation_status == "needs_human_approval"
            or candidate.get("requires_human_approval", False)
            or incident.failure_type == "dependency_error"
        ):
            recovery_result = {
                "status": "needs_human_approval",
                "reason": (
                    "Human approval is required. "
                    "No repair was executed."
                ),
            }

        # Stage 4: Only a passing validation report can reach recovery.
        elif validation_status != "passed":
            recovery_result = {
                "status": "blocked",
                "reason": (
                    "Candidate did not pass sandbox validation. "
                    "Recovery was not executed."
                ),
            }

        else:
            recovery_result = self.recovery_engine.recover(
                incident,
                candidate,
                validation_report,
            )

        return self._result(
            incident,
            rca_result,
            candidate,
            validation_report,
            recovery_result,
            started,
        )
