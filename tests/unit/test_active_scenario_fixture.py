from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_active_scenario_fixture_is_the_expected_32_case_four_family_design():
    fixture_path = ROOT / "benchmarks" / "scenarios" / "trial_cases.yaml"
    document = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    cases = document["cases"]

    assert len(cases) == 32
    assert len({case["case_id"] for case in cases}) == 32
    assert Counter(case["failure_type"] for case in cases) == {
        "schema_change": 8,
        "data_quality": 8,
        "configuration_error": 8,
        "dependency_error": 8,
    }
