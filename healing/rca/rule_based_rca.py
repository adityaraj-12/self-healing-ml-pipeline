from .rca_engine import RCAResult
import ast
import re


class RuleBasedRCA:

    def _get_schema_code(self, message):
        pattern = (
            r"missing=(\[[^\]]*\])"
            r"\s*\|\s*unexpected=(\[[^\]]*\])"
        )

        match = re.search(pattern, message)

        if not match:
            return "schema_mismatch"

        try:
            missing = ast.literal_eval(match.group(1))
            unexpected = ast.literal_eval(match.group(2))
        except (ValueError, SyntaxError):
            return "schema_mismatch"

        if len(missing) == 1 and len(unexpected) == 1:
            return (
                f"schema_rename:{unexpected[0]}->{missing[0]}"
            )

        return "schema_mismatch"


    def _get_config_code(self, message):
        # Framework errors do not use one stable wording. Keep the original
        # high-precision template, then accept common parameter/argument
        # variants without attempting to guess a parameter from unrelated text.
        patterns = (
            r"The ['\"`]([^'\"`]+)['\"`] parameter",
            r"(?:parameter|param)\s+['\"`]?([A-Za-z_]\w*)['\"`]?",
            r"['\"`]([A-Za-z_]\w*)['\"`]\s+(?:parameter|argument)\b",
            r"argument\s+['\"`]?([A-Za-z_]\w*)['\"`]?",
        )
        match = None
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                break

        if match:
            return f"invalid_parameter:{match.group(1)}"

        return "invalid_model_configuration"


    def _get_dependency_code(self, message):
        match = re.search(
            r"No module named ['\"]([^'\"]+)['\"]",
            message
        )

        if match:
            return f"missing_module:{match.group(1)}"

        return "missing_runtime_dependency"

    def _get_data_quality_code(self, message):
        text = message.lower()

        if re.search(r"\b(?:inf|infinity|infinite)\b|non[- ]?finite", text):
            return "invalid_feature_values"

        if any(token in text for token in (
            "non-numeric", "non numeric", "not numeric",
            "string values", "string token", "dtype object", "type mismatch",
            "expected numeric", "numeric value is expected", "not of numeric type",
            "failed to parse", "could not parse", "cannot parse",
            "failed to convert", "could not convert", "cannot convert",
            "conversion error", "incompatible dtype", "incompatible type",
            "integer parse", "float parse", "type error",
        )):
            return "invalid_feature_types"

        if re.search(r"\b(?:nan|na|n/a|null|none|missingness)\b", text) or any(token in text for token in (
            "nan", "missing value", "missing values", "null value",
            "null values", "null entries", "nulls", "none values",
            "contains na", "<na>", "absent values", "absent entries",
            "not a number",
        )):
            return "missing_feature_values"

        return "unclassified_data_quality"

    def analyze(self, incident) -> RCAResult:
        failure_type = incident.failure_type

        message = (
            incident.error_message.lower()
        )

        # -----------------------------------------
        # Schema change
        # -----------------------------------------

        if failure_type == "schema_change":

            return RCAResult(
                failure_type=failure_type,

                root_cause=(
                    "The input schema does not match "
                    "the schema expected by the pipeline."
                ),

                evidence=[
                    "Schema validation failed.",
                    incident.error_message
                ],

                repair_target="input_schema",

                suggested_action=(
                    "Identify the renamed or missing "
                    "column and restore the expected schema."
                ),

                confidence=0.96,

                method="rule_based",

                root_cause_code=self._get_schema_code(
                    incident.error_message
                ),
            )

        # -----------------------------------------
        # Data quality
        # -----------------------------------------

        if failure_type == "data_quality":
            code = self._get_data_quality_code(incident.error_message)

            descriptions = {
                "missing_feature_values": (
                    "Missing values were detected in one or more input features.",
                    "Consider the approved imputation path only after affected columns are confirmed.",
                    0.95,
                ),
                "invalid_feature_values": (
                    "Non-finite numeric values were detected in the input features.",
                    "Do not treat infinity as missing data; inspect and normalize the source values before selecting a repair.",
                    0.90,
                ),
                "invalid_feature_types": (
                    "One or more input features do not have the expected numeric type.",
                    "Inspect type conversion and source-schema evidence; median imputation alone is not an appropriate type repair.",
                    0.90,
                ),
                "unclassified_data_quality": (
                    "A data-quality failure was reported, but the available message does not identify a supported subtype.",
                    "Collect additional data-quality evidence and request review rather than assuming missing values.",
                    0.50,
                ),
            }
            root_cause, suggested_action, confidence = descriptions[code]

            return RCAResult(
                failure_type=failure_type,
                root_cause=root_cause,
                evidence=[
                    f"Data-quality code assigned: {code}.",
                    incident.error_message,
                ],
                repair_target="input_data",
                suggested_action=suggested_action,
                confidence=confidence,
                method="rule_based",
                root_cause_code=code,
            )

        # -----------------------------------------
        # Configuration
        # -----------------------------------------

        if failure_type == "configuration_error":

            return RCAResult(
                failure_type=failure_type,

                root_cause=(
                    "An invalid model or pipeline "
                    "configuration parameter caused "
                    "training to fail."
                ),

                evidence=[
                    "Model configuration contains "
                    "an invalid parameter value.",
                    incident.error_message
                ],

                repair_target="model_configuration",

                suggested_action=(
                    "Identify the invalid parameter "
                    "and replace it with a valid value."
                ),

                confidence=0.98,

                method="rule_based",

                root_cause_code=self._get_config_code(
                    incident.error_message
                ),
            )

        # -----------------------------------------
        # Dependency
        # -----------------------------------------

        if failure_type == "dependency_error":

            return RCAResult(
                failure_type=failure_type,

                root_cause=(
                    "A required Python module or runtime "
                    "dependency is unavailable."
                ),

                evidence=[
                    "Runtime import failed.",
                    incident.error_message
                ],

                repair_target="runtime_dependencies",

                suggested_action=(
                    "Identify the missing dependency and "
                    "restore a compatible runtime dependency."
                ),

                confidence=0.99,

                method="rule_based",

                root_cause_code=self._get_dependency_code(
                    incident.error_message
                ),
            )

        # -----------------------------------------
        # Unknown
        # -----------------------------------------

        return RCAResult(
            failure_type=failure_type,

            root_cause=(
                "The available runtime evidence is "
                "insufficient to determine the exact cause."
            ),

            evidence=[
                incident.error_message
            ],

            repair_target="unknown",

            suggested_action=(
                "Collect additional runtime and "
                "pipeline context before generating a repair."
            ),

            confidence=0.40,

            method="rule_based",

            root_cause_code="unknown",
        )