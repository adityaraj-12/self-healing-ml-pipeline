import json
from types import SimpleNamespace

from healing.rca.rule_based_rca import RuleBasedRCA


def make_incident(failure_type, error_message):
    return SimpleNamespace(
        failure_type=failure_type,
        error_message=error_message,
    )


def test_rca_identifies_schema_rename():
    incident = make_incident(
        "schema_change",
        "Schema mismatch | missing=['mean radius'] "
        "| unexpected=['mean_radius']",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.failure_type == "schema_change"
    assert result.root_cause_code == (
        "schema_rename:mean_radius->mean radius"
    )
    assert result.repair_target == "input_schema"
    assert result.method == "rule_based"
    assert result.confidence == 0.96
    assert len(result.evidence) >= 2


def test_rca_handles_general_schema_mismatch():
    incident = make_incident(
        "schema_change",
        "Schema mismatch: incompatible input columns",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.root_cause_code == "schema_mismatch"
    assert result.repair_target == "input_schema"


def test_rca_identifies_missing_feature_values():
    incident = make_incident(
        "data_quality",
        "Input contains NaN values",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.failure_type == "data_quality"
    assert result.root_cause_code == "missing_feature_values"
    assert result.repair_target == "input_data"
    assert result.method == "rule_based"
    assert result.confidence == 0.95
    assert len(result.evidence) >= 2


def test_rca_identifies_invalid_configuration_parameter():
    incident = make_incident(
        "configuration_error",
        "The 'C' parameter must be a positive float",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.failure_type == "configuration_error"
    assert result.root_cause_code == "invalid_parameter:C"
    assert result.repair_target == "model_configuration"
    assert result.method == "rule_based"
    assert result.confidence == 0.98
    assert len(result.evidence) >= 2


def test_rca_identifies_missing_dependency():
    incident = make_incident(
        "dependency_error",
        "No module named 'fake_package'",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.failure_type == "dependency_error"
    assert result.root_cause_code == "missing_module:fake_package"
    assert result.method == "rule_based"
    assert result.confidence == 0.99
    assert len(result.evidence) >= 2


def test_rca_result_serialization():
    incident = make_incident(
        "data_quality",
        "Missing values detected",
    )

    result = RuleBasedRCA().analyze(incident)

    result_dict = result.to_dict()
    result_json = result.to_json()
    decoded = json.loads(result_json)

    assert decoded == result_dict
    assert decoded["root_cause_code"] == "missing_feature_values"
    assert decoded["repair_target"] == "input_data"


def test_rca_distinguishes_non_finite_feature_values():
    incident = make_incident(
        "data_quality",
        "Input matrix contains positive infinity values",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.root_cause_code == "invalid_feature_values"
    assert "Do not treat infinity as missing data" in result.suggested_action


def test_rca_distinguishes_feature_type_mismatch():
    incident = make_incident(
        "data_quality",
        "Feature 'mean radius' contains string values where numeric values are required",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.root_cause_code == "invalid_feature_types"
    assert "median imputation alone" in result.suggested_action


def test_rca_keeps_unknown_data_quality_subtype_unclassified():
    incident = make_incident(
        "data_quality",
        "Rows include unsupported sentinel code -9999",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.root_cause_code == "unclassified_data_quality"
    assert result.confidence == 0.50


def test_rca_handles_string_token_where_number_is_expected():
    incident = make_incident(
        "data_quality",
        "A string token was supplied where a numeric value is expected.",
    )

    result = RuleBasedRCA().analyze(incident)

    assert result.root_cause_code == "invalid_feature_types"
