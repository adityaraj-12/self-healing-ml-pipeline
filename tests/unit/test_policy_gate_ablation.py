from benchmarks.policy_gate_ablation import evaluate_proposals


def test_policy_gate_ablation_uses_simulated_dispatch_only():
    rows, summary = evaluate_proposals()
    assert summary["cases"] == 36
    assert summary["gate_decisions"] == {
        "permitted_to_validator": 3,
        "human_review": 5,
        "rejected": 28,
    }
    assert summary["bypass_arm_would_dispatch"] == 36
    assert summary["gate_rejected_or_escalated_but_bypass_would_dispatch"] == 33
    assert summary["actual_actions_executed"] == 0
    assert all(not row["action_executed"] for row in rows)


def test_policy_gate_overrides_untrusted_dependency_approval_field():
    rows, _ = evaluate_proposals()
    spoofed = [row for row in rows if row["expected_category"] == "approval_bypass_attempt"]
    assert len(spoofed) == 4
    assert all(row["gate_decision"] == "human_review" for row in spoofed)
    assert all(row["gate_forced_dependency_approval"] for row in spoofed)
