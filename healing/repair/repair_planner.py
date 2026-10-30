import ast
import re


class RepairPlanner:

    def _extract_list(self, message, name):
        pattern = rf"{re.escape(name)}=(\[[^\]]*\])"
        match = re.search(pattern, message)

        if not match:
            return []

        try:
            value = ast.literal_eval(match.group(1))
        except (ValueError, SyntaxError):
            return []

        return value if isinstance(value, list) else []

    def plan(self, incident, rca):
        failure_type = incident.failure_type
        message = incident.error_message

        evidence = list(rca.evidence)

        # -----------------------------------------
        # F1: Schema change
        # -----------------------------------------
        if failure_type == "schema_change":
            missing = self._extract_list(
                message, "missing"
            )
            unexpected = self._extract_list(
                message, "unexpected"
            )

            if len(missing) == 1 and len(unexpected) == 1:
                return {
                    "action": "rename_column",
                    "target": "input_data",
                    "parameters": {
                        "column_mapping": {
                            unexpected[0]: missing[0]
                        },
                        "semantic_equivalence_required": True
                    },
                    "rationale": (
                        "One expected column is missing and "
                        "one unexpected column is present. "
                        "A rename is a candidate explanation, "
                        "not yet a confirmed repair."
                    ),
                    "evidence": evidence + [
                        f"Missing columns: {missing}",
                        f"Unexpected columns: {unexpected}"
                    ],
                    "validation_checks": [
                        "Confirm the column mapping is semantically valid.",
                        "Apply the rename only to an isolated data copy.",
                        "Verify the repaired schema matches the expected schema.",
                        "Verify row count and feature values are preserved.",
                        "Run the affected pipeline stage again."
                    ],
                    "risks": [
                        "Similar column names do not guarantee equivalent meaning.",
                        "A rename could conceal a genuine upstream data change."
                    ],
                    "requires_human_approval": False
                }

            return {
                "action": "reconcile_schema",
                "target": "input_data",
                "parameters": {
                    "missing_columns": missing,
                    "unexpected_columns": unexpected
                },
                "rationale": (
                    "The schema mismatch cannot be resolved "
                    "confidently using a single unambiguous mapping."
                ),
                "evidence": evidence,
                "validation_checks": [
                    "Determine intended column correspondence.",
                    "Check column types and value semantics.",
                    "Validate the complete repaired schema."
                ],
                "risks": [
                    "Incorrect column mapping may corrupt feature meaning."
                ],
                "requires_human_approval": True
            }

        # -----------------------------------------
        # F2: Data-quality failure
        # -----------------------------------------
        if failure_type == "data_quality":
            if getattr(rca, "root_cause_code", None) != "missing_feature_values":
                return {
                    "action": "manual_diagnosis",
                    "target": "input_data",
                    "parameters": {},
                    "rationale": (
                        "The detected data-quality subtype is outside the "
                        "implemented missing-value imputation policy."
                    ),
                    "evidence": evidence + [message],
                    "validation_checks": [
                        "Identify the exact invalid-value or type condition.",
                        "Define a subtype-specific repair before automatic execution.",
                    ],
                    "risks": [
                        "Applying median imputation to non-finite values or type mismatches may not correct the underlying data defect."
                    ],
                    "requires_human_approval": True,
                }

            return {
                "action": "impute_missing_values",
                "target": "input_data",
                "parameters": {
                    "column_scope": "columns_with_missing_values",
                    "numeric_strategy": "median",
                    "categorical_strategy": "most_frequent",
                    "exclude_target_column": True
                },
                "rationale": (
                    "The runtime error indicates invalid or missing "
                    "feature values. A candidate is to identify "
                    "affected columns and apply type-appropriate "
                    "imputation."
                ),
                "evidence": evidence + [message],
                "validation_checks": [
                    "Identify which columns contain missing values.",
                    "Fit imputers on training data only.",
                    "Ensure the target column is not modified.",
                    "Verify no invalid feature values remain.",
                    "Verify feature schema and row count are preserved.",
                    "Retrain and evaluate the pipeline."
                ],
                "risks": [
                    "Imputation may distort data distributions.",
                    "The appropriate strategy depends on why values are missing."
                ],
                "requires_human_approval": False
            }

        # -----------------------------------------
        # F3: Configuration failure
        # -----------------------------------------
        if failure_type == "configuration_error":
            current = incident.pipeline_config or {}

            baseline = (
                incident.context.get("baseline_config", {})
                .get("model", {})
            )

            changes = []

            for parameter, current_value in current.items():
                if (
                    parameter in baseline
                    and baseline[parameter] != current_value
                ):
                    changes.append({
                        "parameter": parameter,
                        "observed_value": current_value,
                        "proposed_value": baseline[parameter]
                    })

            if not changes:
                return {
                    "action": "inspect_configuration",
                    "target": "model_configuration",
                    "parameters": {
                        "current_configuration": current,
                        "baseline_available": bool(baseline)
                    },
                    "rationale": (
                        "The current configuration failed, but no "
                        "changed parameter could be safely identified "
                        "from the available baseline."
                    ),
                    "evidence": evidence + [message],
                    "validation_checks": [
                        "Identify the invalid parameter.",
                        "Compare it with documented valid constraints.",
                        "Test a candidate configuration in isolation."
                    ],
                    "risks": [
                        "Changing a parameter may alter model performance."
                    ],
                    "requires_human_approval": True
                }

            return {
                "action": "restore_configuration",
                "target": "model_configuration",
                "parameters": {
                    "changes": changes
                },
                "rationale": (
                    "The failed configuration differs from the "
                    "preserved baseline. Restoring the changed "
                    "parameter is a testable repair candidate."
                ),
                "evidence": evidence + [message],
                "validation_checks": [
                    "Verify proposed values satisfy model constraints.",
                    "Apply changes only in an isolated configuration.",
                    "Rerun training and evaluation.",
                    "Compare results with the healthy baseline."
                ],
                "risks": [
                    "The previous configuration may not be appropriate "
                    "if the surrounding environment has changed."
                ],
                "requires_human_approval": False
            }

        # -----------------------------------------
        # F4: Dependency/runtime failure
        # -----------------------------------------
        if failure_type == "dependency_error":
            match = re.search(
                r"No module named ['\"]([^'\"]+)['\"]",
                message
            )
            module = match.group(1) if match else None

            return {
                "action": "verify_dependency",
                "target": "runtime_dependencies",
                "parameters": {
                    "missing_module": module,
                    "automatic_install": False,
                    "check_requirements": True,
                    "check_import_name_mapping": True
                },
                "rationale": (
                    "A dependency/import error requires checking "
                    "the project manifest and import-to-package mapping "
                    "before selecting a corrective action."
                ),
                "evidence": evidence + [message],
                "validation_checks": [
                    "Check requirements.txt and pyproject.toml.",
                    "Verify whether the module is intentionally required.",
                    "Verify package name and import name correspondence.",
                    "Test changes in an isolated environment."
                ],
                "risks": [
                    "Installing an arbitrary package may introduce "
                    "security or compatibility problems.",
                    "A simulated missing module may not correspond "
                    "to a real installable package."
                ],
                "requires_human_approval": True
            }

        # -----------------------------------------
        # Unknown failure
        # -----------------------------------------
        return {
            "action": "manual_diagnosis",
            "target": "unknown",
            "parameters": {},
            "rationale": (
                "The current repair planner does not have a safe, "
                "supported action for this failure type."
            ),
            "evidence": evidence + [message],
            "validation_checks": [
                "Collect additional pipeline evidence.",
                "Determine the failure's root cause before proposing a repair."
            ],
            "risks": [
                "Attempting an unsupported repair may introduce new failures."
            ],
            "requires_human_approval": True
        }