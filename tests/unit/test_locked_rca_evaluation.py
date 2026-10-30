import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "data" / "rca_locked_v1.json"
SOURCE = ROOT / "healing" / "rca" / "rule_based_rca.py"


def test_locked_rca_fixture_matches_frozen_implementation_hash():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert actual == fixture["rule_implementation_sha256"]
    assert fixture["status"] == "locked_before_evaluation"
    assert len(fixture["cases"]) == 36


def test_locked_rca_score_is_reproducible_without_llm_calls():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rca = RuleBasedRCA()
    correct = 0
    for case in fixture["cases"]:
        incident = SimpleNamespace(
            incident_id=f"TEST-{case['case_id']}",
            failure_type=case["failure_type"],
            error_message=case["error_message"],
        )
        correct += rca.analyze(incident).root_cause_code == case["expected_root_cause_code"]
    assert correct == 33
