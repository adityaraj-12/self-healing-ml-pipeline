import json

import pytest

from benchmarks.failure_stress_challenge import main as run_stress_challenge
from benchmarks.seed_sensitivity import main as run_seed_sensitivity


def test_expanded_seed_sensitivity_labels_active_templates_and_preserves_output(tmp_path):
    output = tmp_path / "seed_sensitivity.json"

    result = run_seed_sensitivity(n_seeds=1, output_path=output)

    assert output.exists()
    assert result["experiment_id"] == "deterministic-repair-split-sensitivity-v2-expanded"
    assert result["fault_template_count"] == 24
    assert len(result["fault_template_ids"]) == 24
    assert result["trials"] == 24
    assert result["validation_passes"] == result["trials"]
    assert "24 active project-authored" in result["interpretation"]
    assert json.loads(output.read_text())["trials"] == 24

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        run_seed_sensitivity(n_seeds=1, output_path=output)


def test_stress_challenge_refuses_to_overwrite_explicit_output(tmp_path):
    output = tmp_path / "existing_stress_result.json"
    original = '{"preserve": true}\n'
    output.write_text(original)

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        run_stress_challenge(output_path=output)

    assert output.read_text() == original
