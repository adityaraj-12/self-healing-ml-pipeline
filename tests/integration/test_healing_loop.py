from types import SimpleNamespace

from healing.recovery.recovery_engine import RecoveryEngine


def make_incident(
    incident_id="INC-TEST",
    failure_type="data_quality",
):
    return SimpleNamespace(
        incident_id=incident_id,
        failure_type=failure_type,
        context={},
    )



def make_candidate(
    incident_id="INC-TEST",
    failure_type="data_quality",
    candidate_id="RC-TEST",
    requires_human_approval=False,
):
    actions = {
        "schema_change": "rename_column",
        "data_quality": "impute_missing_values",
        "configuration_error": "restore_configuration",
        "dependency_error": "verify_dependency",
    }

    return {
        "candidate_id": candidate_id,
        "incident_id": incident_id,
        "failure_type": failure_type,
        "action": actions[failure_type],
        "parameters": {},
        "requires_human_approval": requires_human_approval,
    }



def test_recovery_blocks_candidate_when_validation_fails():
    engine = RecoveryEngine()
    incident = make_incident()
    candidate = make_candidate()

    report = {
        "status": "failed",
        "candidate_id": candidate["candidate_id"],
        "incident_id": incident.incident_id,
        "reason": "Sandbox checks failed.",
    }

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "blocked"


def test_recovery_blocks_mismatched_validation_report():
    engine = RecoveryEngine()
    incident = make_incident()
    candidate = make_candidate()

    report = {
        "status": "passed",
        "candidate_id": "RC-OTHER",
        "incident_id": incident.incident_id,
    }

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "blocked"
    assert "does not match" in result["reason"]


def test_dependency_repair_requires_human_approval():
    engine = RecoveryEngine()
    incident = make_incident(
        failure_type="dependency_error"
    )
    candidate = make_candidate(
        failure_type="dependency_error",
        requires_human_approval=True,
    )

    report = {
        "status": "needs_human_approval",
        "candidate_id": candidate["candidate_id"],
        "incident_id": incident.incident_id,
    }

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "needs_human_approval"


def test_candidate_policy_can_require_approval():
    engine = RecoveryEngine()
    incident = make_incident()
    candidate = make_candidate(
        requires_human_approval=True
    )

    report = {
        "status": "passed",
        "candidate_id": candidate["candidate_id"],
        "incident_id": incident.incident_id,
    }

    result = engine.recover(incident, candidate, report)

    assert result["status"] == "needs_human_approval"


def test_orchestrator_does_not_execute_unvalidated_candidate():
    from healing.orchestrator import HealingOrchestrator

    incident = make_incident()
    candidate = make_candidate()

    class FakeRCA:
        def analyze(self, incident):
            return SimpleNamespace(
                to_dict=lambda: {"failure_type": incident.failure_type}
            )

    class FakeGenerator:
        def generate(self, incident, rca):
            return SimpleNamespace(to_dict=lambda: candidate)

    class FakeValidator:
        def validate(self, candidate, incident):
            return {
                "candidate_id": candidate["candidate_id"],
                "incident_id": incident.incident_id,
                "status": "failed",
                "reason": "Deliberately failed safety check.",
            }

    class FakeRecovery:
        called = False

        def recover(self, incident, candidate, report):
            self.called = True
            return {"status": "recovered"}

    recovery = FakeRecovery()

    orchestrator = HealingOrchestrator(
        rca=FakeRCA(),
        repair_generator=FakeGenerator(),
        validator=FakeValidator(),
        recovery_engine=recovery,
    )

    result = orchestrator.run(incident)

    assert result["status"] == "blocked"
    assert result["recovery_result"]["status"] == "blocked"
    assert recovery.called is False


def test_orchestrator_executes_only_after_validation_passes():
    from healing.orchestrator import HealingOrchestrator

    incident = make_incident()
    candidate = make_candidate()

    class FakeRCA:
        def analyze(self, incident):
            return SimpleNamespace(
                to_dict=lambda: {"failure_type": incident.failure_type}
            )

    class FakeGenerator:
        def generate(self, incident, rca):
            return SimpleNamespace(to_dict=lambda: candidate)

    class FakeValidator:
        def validate(self, candidate, incident):
            return {
                "candidate_id": candidate["candidate_id"],
                "incident_id": incident.incident_id,
                "status": "passed",
            }

    class FakeRecovery:
        called = False

        def recover(self, incident, candidate, report):
            self.called = True
            return {"status": "recovered"}

    recovery = FakeRecovery()

    orchestrator = HealingOrchestrator(
        rca=FakeRCA(),
        repair_generator=FakeGenerator(),
        validator=FakeValidator(),
        recovery_engine=recovery,
    )

    result = orchestrator.run(incident)

    assert result["status"] == "recovered"
    assert recovery.called is True


def test_orchestrator_never_executes_dependency_repair():
    from healing.orchestrator import HealingOrchestrator

    incident = make_incident(
        failure_type="dependency_error"
    )
    candidate = make_candidate(
        failure_type="dependency_error",
        requires_human_approval=True,
    )

    class FakeRCA:
        def analyze(self, incident):
            return SimpleNamespace(
                to_dict=lambda: {"failure_type": incident.failure_type}
            )

    class FakeGenerator:
        def generate(self, incident, rca):
            return SimpleNamespace(to_dict=lambda: candidate)

    class FakeValidator:
        def validate(self, candidate, incident):
            return {
                "candidate_id": candidate["candidate_id"],
                "incident_id": incident.incident_id,
                "status": "needs_human_approval",
            }

    class FakeRecovery:
        called = False

        def recover(self, incident, candidate, report):
            self.called = True
            return {"status": "recovered"}

    recovery = FakeRecovery()

    orchestrator = HealingOrchestrator(
        rca=FakeRCA(),
        repair_generator=FakeGenerator(),
        validator=FakeValidator(),
        recovery_engine=recovery,
    )

    result = orchestrator.run(incident)

    assert result["status"] == "needs_human_approval"
    assert recovery.called is False
