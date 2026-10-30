import ast
import json
import os
import re

from healing.repair.repair_candidate import RepairCandidate
from healing.repair.llm_io_capture import capture_failure, capture_success


class LLMRepairGenerator:

    ALLOWED_ACTIONS = {
        "schema_change": "rename_column",
        "data_quality": "impute_missing_values",
        "configuration_error": "restore_configuration",
        "dependency_error": "verify_dependency",
    }

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        base_url = os.getenv("OPENAI_BASE_URL")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        if not model:
            raise RuntimeError(
                "OPENAI_MODEL is not configured."
            )

        # Import the optional SDK lazily. This lets offline tooling and the
        # manifest/preflight path run without the live-LLM extra installed.
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI Python SDK is not installed. Install the optional "
                "LLM dependencies with: python -m pip install -r requirements-llm.txt"
            ) from exc

        if base_url:
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )
        else:
            self.client = OpenAI(api_key=api_key)

        self.model = model

    def _extract_schema_difference(self, message):
        pattern = (
            r"missing=(\[[^\]]*\])"
            r"\s*\|\s*unexpected=(\[[^\]]*\])"
        )

        match = re.search(pattern, message)

        if not match:
            return [], []

        try:
            missing = ast.literal_eval(match.group(1))
            unexpected = ast.literal_eval(match.group(2))
        except (ValueError, SyntaxError):
            return [], []

        if not isinstance(missing, list):
            return [], []

        if not isinstance(unexpected, list):
            return [], []

        return missing, unexpected

    def _validate_plan(self, incident, plan):
        if not isinstance(plan, dict):
            raise ValueError("Repair plan must be a JSON object.")

        allowed_plan_keys = {
            "action", "parameters", "rationale", "evidence",
            "validation_checks", "risks", "requires_human_approval",
        }
        unexpected_plan_keys = set(plan) - allowed_plan_keys
        if unexpected_plan_keys:
            raise ValueError(
                f"Unrecognized repair-plan fields: {sorted(unexpected_plan_keys)}"
            )

        failure_type = incident.failure_type

        if failure_type not in self.ALLOWED_ACTIONS:
            raise ValueError(
                f"Unsupported failure type: {failure_type}"
            )

        expected_action = self.ALLOWED_ACTIONS[failure_type]

        if plan.get("action") != expected_action:
            raise ValueError(
                f"Unsupported action for {failure_type}. "
                f"Expected {expected_action}."
            )

        params = plan.get("parameters")

        if not isinstance(params, dict):
            raise ValueError(
                "Repair parameters must be a JSON object."
            )

        allowed_parameter_keys = {
            "schema_change": {"column_mapping", "semantic_equivalence_required"},
            "data_quality": {"column_scope", "numeric_strategy", "categorical_strategy", "exclude_target_column"},
            "configuration_error": {"changes"},
            "dependency_error": {"missing_module", "automatic_install", "check_requirements", "check_import_name_mapping"},
        }[failure_type]
        unexpected_parameter_keys = set(params) - allowed_parameter_keys
        if unexpected_parameter_keys:
            raise ValueError(
                f"Unrecognized repair parameter fields: {sorted(unexpected_parameter_keys)}"
            )

        if failure_type == "schema_change":
            missing, unexpected = (
                self._extract_schema_difference(
                    incident.error_message
                )
            )

            if len(missing) != 1 or len(unexpected) != 1:
                raise ValueError(
                    "Schema difference is ambiguous. "
                    "A safe one-to-one rename cannot be inferred."
                )

            expected_mapping = {
                unexpected[0]: missing[0]
            }

            proposed_mapping = params.get("column_mapping")

            if proposed_mapping != expected_mapping:
                raise ValueError(
                    "Proposed column mapping does not match "
                    "the observed schema difference. "
                    f"Expected: {expected_mapping!r}. "
                    f"Received: {proposed_mapping!r}. "
                    "Mapping must use source_column -> target_column."
                )

            # Do not infer semantic equivalence from names alone.
            params["semantic_equivalence_required"] = True

        elif failure_type == "data_quality":
            if (
                params.get("column_scope")
                != "columns_with_missing_values"
                or params.get("numeric_strategy") != "median"
                or params.get("categorical_strategy")
                != "most_frequent"
                or params.get("exclude_target_column") is not True
            ):
                raise ValueError(
                    "Data repair proposal does not match "
                    "the permitted imputation policy."
                )

        elif failure_type == "configuration_error":
            current = incident.pipeline_config or {}

            baseline = (
                incident.context.get("baseline_config", {})
                .get("model", {})
            )

            changes = params.get("changes", [])

            if not isinstance(changes, list) or not changes:
                raise ValueError(
                    "Configuration repair needs a non-empty change list."
                )

            for change in changes:
                if not isinstance(change, dict):
                    raise ValueError(
                        "Every configuration change must be an object."
                    )
                unexpected_change_keys = set(change) - {"parameter", "observed_value", "proposed_value"}
                if unexpected_change_keys:
                    raise ValueError(
                        f"Unrecognized configuration-change fields: {sorted(unexpected_change_keys)}"
                    )

                parameter = change.get("parameter")

                if parameter not in current or parameter not in baseline:
                    raise ValueError(
                        f"Unknown or ungrounded parameter: {parameter}"
                    )

                if change.get("observed_value") != current[parameter]:
                    raise ValueError(
                        f"Observed value mismatch for {parameter}."
                    )

                if change.get("proposed_value") != baseline[parameter]:
                    raise ValueError(
                        f"Proposed value for {parameter} must match "
                        "the preserved healthy baseline."
                    )

        elif failure_type == "dependency_error":
            if params.get("automatic_install") is not False:
                raise ValueError(
                    "Automatic dependency installation is prohibited."
                )

            match = re.search(
                r"No module named ['\"]([^'\"]+)['\"]",
                incident.error_message
            )

            observed_module = match.group(1) if match else None

            if (
                observed_module
                and params.get("missing_module") != observed_module
            ):
                raise ValueError(
                    "Proposed module does not match the observed error."
                )

            plan["requires_human_approval"] = True

        # Prevent malformed or overly broad proposals.
        if not isinstance(plan.get("evidence"), list):
            raise ValueError("Evidence must be a list.")

        if not isinstance(plan.get("validation_checks"), list):
            raise ValueError("Validation checks must be a list.")

        if not isinstance(plan.get("risks"), list):
            raise ValueError("Risks must be a list.")

        if not isinstance(plan.get("rationale"), str):
            raise ValueError("Rationale must be a string.")

        plan["target"] = {
            "schema_change": "input_data",
            "data_quality": "input_data",
            "configuration_error": "model_configuration",
            "dependency_error": "runtime_dependencies",
        }[failure_type]

        plan["generator"] = "llm"

        return plan

    def generate(self, incident, rca):
        incident_data = incident.to_dict()
        rca_data = rca.to_dict()

        failure_type = incident.failure_type
        if (
            failure_type == "data_quality"
            and getattr(rca, "root_cause_code", None) != "missing_feature_values"
        ):
            raise ValueError(
                "The current automatic data-repair policy supports missing-value "
                "imputation only. Non-finite values, type mismatches, and "
                "unclassified data-quality faults require manual review."
            )
        action_instruction = ""

        if failure_type == "schema_change":
            missing, unexpected = self._extract_schema_difference(
                incident.error_message
            )

            if len(missing) != 1 or len(unexpected) != 1:
                raise ValueError(
                    "Schema mismatch is ambiguous; "
                    "cannot propose a single-column rename."
                )

            mapping = {
                unexpected[0]: missing[0]
            }

            action_instruction = f"""
        Required action: rename_column

        The parameters object MUST contain:
        {json.dumps({
            "column_mapping": mapping,
            "semantic_equivalence_required": True
        }, indent=2)}

        Use existing_column -> expected_column.
        Do not reverse the mapping.
        """

        elif failure_type == "configuration_error":
            current = incident.pipeline_config or {}

            baseline = (
                incident.context.get("baseline_config", {})
                .get("model", {})
            )

            changes = [
                {
                    "parameter": parameter,
                    "observed_value": current[parameter],
                    "proposed_value": baseline[parameter]
                }
                for parameter in current
                if parameter in baseline
                and current[parameter] != baseline[parameter]
            ]

            if not changes:
                raise ValueError(
                    "No changed model parameter was found in the "
                    "incident and its preserved baseline configuration. "
                    "Inspect the incident context before generating a repair."
                )

            action_instruction = f"""
        Required action: restore_configuration

        The parameters object MUST have this exact structure:
        {json.dumps({"changes": changes}, indent=2)}

        Use only these evidence-backed changes.
        Preserve JSON value types: do not convert numbers to strings.
        Do not use column_mapping, update_parameter, or any other action.
        Do not invent alternative parameter values.
        """

        elif failure_type == "data_quality":
            action_instruction = """
        Required action: impute_missing_values

        The parameters object MUST be:
        {
        "column_scope": "columns_with_missing_values",
        "numeric_strategy": "median",
        "categorical_strategy": "most_frequent",
        "exclude_target_column": true
        }

        Do not propose other imputation strategies.
        """

        elif failure_type == "dependency_error":
            match = re.search(
                r"No module named ['\"]([^'\"]+)['\"]",
                incident.error_message
            )
            module = match.group(1) if match else None

            action_instruction = f"""
        Required action: verify_dependency

        The parameters object MUST contain:
        {json.dumps({
            "missing_module": module,
            "automatic_install": False,
            "check_requirements": True,
            "check_import_name_mapping": True
        }, indent=2)}

        Human approval is required. Do not install packages.
        """

        else:
            raise ValueError(
                f"Unsupported failure type: {failure_type}"
            )

        prompt = f"""
        Generate one evidence-grounded repair candidate.

        INCIDENT:
        {json.dumps(incident.to_dict(), indent=2)}

        ROOT-CAUSE ANALYSIS:
        {json.dumps(rca.to_dict(), indent=2)}

        FAILURE-SPECIFIC REQUIREMENTS:
        {action_instruction}

        Return one valid JSON object with these top-level keys:
        - action
        - parameters
        - rationale
        - evidence
        - validation_checks
        - risks
        - requires_human_approval

        Requirements:
        1. Follow the failure-specific action and parameters format exactly.
        2. Do not reuse parameter fields belonging to another failure type.
        3. Use only the incident evidence and preserved baseline.
        4. Do not generate Python code or shell commands.
        5. Do not execute or apply the proposed repair.
        6. Evidence, validation_checks and risks must be JSON arrays of strings.
        7. Return JSON only.
        """


        messages = [
            {
                "role": "system",
                "content": (
                    "You generate evidence-grounded ML pipeline repair "
                    "proposals. Follow the permitted action contract. "
                    "Never execute a repair."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        for attempt in range(2):
            request_payload = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            try:
                response = self.client.chat.completions.create(**request_payload)
            except Exception as exc:
                capture_failure(request_payload, exc, attempt + 1)
                raise
            capture_success(request_payload, response, attempt + 1)

            content = response.choices[0].message.content

            if not content:
                raise ValueError("The LLM returned an empty response.")

            try:
                plan = json.loads(content)

                if not isinstance(plan, dict):
                    raise ValueError(
                        "The repair plan must be a JSON object."
                    )

                plan = self._validate_plan(incident, plan)

                candidate = RepairCandidate.create(
                    incident=incident,
                    plan=plan
                )

                print(
                    f"LLM repair candidate validated structurally "
                    f"on attempt {attempt + 1}."
                )

                return candidate

            except (ValueError, TypeError, KeyError) as exc:
                print(f"\nLLM candidate rejected on attempt {attempt + 1}:", flush=True)
                print(f"Reason: {exc}", flush=True)
                print(
                    "Raw response omitted from console output; inspect the protected "
                    "LLM capture log if enabled.",
                    flush=True,
                )
                if attempt == 1:
                    raise ValueError(
                        "LLM repair candidate failed structural "
                        f"validation after 2 attempts: {exc}"
                    ) from exc

                # Give the model the exact validation feedback.
                messages.append({
                    "role": "assistant",
                    "content": content
                })

                messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous candidate failed validation: {exc}\n\n"
                        f"Required action-specific contract:\n{action_instruction}\n\n"
                        "Return corrected JSON using this contract exactly. "
                        "Preserve numeric values as numbers, not strings. "
                        "Do not use fields from another failure type."
                    )
                })

        raise RuntimeError("Unexpected end of repair-generation loop.")
