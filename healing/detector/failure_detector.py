"""Rule-based failure-family classification from exception evidence.

This component intentionally does not consult injected-fault metadata stored in
incident context. Context is limited to runtime stage information used to make
ambiguous KeyError handling more conservative.
"""

import re


class FailureDetector:
    """Classify supported failure families or abstain as unknown."""

    _DEPENDENCY_PATTERNS = (
        r"\bno module named\b",
        r"\bcannot import name\b",
        r"\bcannot import\b",
        r"\bfailed to import\b",
        r"\bdll load failed\b",
        r"\bshared object file\b",
        r"\bshared library\b.*\bnot found\b",
        r"\bdependency conflict\b",
        r"\bincompatible (?:package|dependency) version\b",
    )
    _SCHEMA_PATTERNS = (
        r"\bschema mismatch\b",
        r"\bmissing\s*=\s*\[.*\]\s*\|\s*unexpected\s*=\s*\[.*\]",
        r"\bcolumn\b.*\bnot found\b",
        r"\bfeature names?\b.*\b(?:must|should) match\b",
        r"\b(?:expected|unexpected) feature names?\b",
        r"\bcolumns? (?:are )?(?:missing|unexpected)\b",
        r"\binput columns? do not match\b",
    )
    _DATA_QUALITY_PATTERNS = (
        r"\bcontains?\s+(?:nan|nans|na|nas|null|nulls|none values)\b",
        r"\bmissing values?\b",
        r"\bnull values?\b",
        r"\b(?:positive |negative )?infinity\b",
        r"\bnon[- ]?finite\b",
        r"\bobject dtype\b",
        r"\bdtype object\b",
        r"\bstring values?\b.*\bnumeric\b",
        r"\bstring token\b.*\bnumeric\b",
        r"\bcould not convert string to float\b",
        r"\bfailed to parse\b",
        r"\bincompatible dtype\b",
        r"\btype mismatch\b",
        r"\bnot of numeric type\b",
        r"\bexpected numeric\b",
    )
    _CONFIG_PATTERNS = (
        r"\binvalid parameter\b",
        r"\bparameter\b.*\bmust be\b",
        r"\bparameter\b.*\bmust be one of\b",
        r"\bunexpected keyword argument\b",
        r"\bunsupported parameter\b",
        r"\binvalid configuration\b",
    )

    @staticmethod
    def _result(failure_type, confidence, reason):
        return {
            "failure_type": failure_type,
            "confidence": confidence,
            "reason": reason,
        }

    @staticmethod
    def _matches(patterns, message):
        return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in patterns)

    def detect(self, exception, context=None):
        """Classify an exception without consulting injected ground-truth labels.

        Args:
            exception: The caught exception.
            context: Optional runtime context. Only ``runtime.current_stage`` is
                consulted. ``failure_injection`` and any ground-truth fields are
                intentionally ignored to avoid label leakage.
        """
        context = context or {}
        exception_type = type(exception).__name__
        message = str(exception).strip().lower()
        runtime = context.get("runtime", {}) if isinstance(context, dict) else {}
        stage = str(runtime.get("current_stage", "")).lower()

        # Import-specific evidence takes precedence over generic missing-key text.
        if exception_type in {"ModuleNotFoundError", "ImportError"} or self._matches(
            self._DEPENDENCY_PATTERNS, message
        ) or "dependency" in message:
            return self._result(
                "dependency_error",
                0.99,
                "Dependency or import failure detected from exception evidence.",
            )

        if self._matches(self._SCHEMA_PATTERNS, message):
            return self._result(
                "schema_change",
                0.95,
                "Schema-related error detected from explicit column or feature evidence.",
            )

        # A KeyError is not automatically a schema problem: missing files,
        # artifact IDs, and application keys also raise KeyError. Require feature
        # or schema context before assigning this family.
        if exception_type == "KeyError" and (
            any(token in message for token in ("feature", "column", "schema"))
            or any(token in stage for token in ("schema", "feature", "preprocess"))
        ):
            return self._result(
                "schema_change",
                0.80,
                "KeyError occurred with feature/schema evidence in the message or stage.",
            )

        if self._matches(self._DATA_QUALITY_PATTERNS, message):
            # Preserve established confidence values for the original benchmark
            # message while using a more conservative value for broader patterns.
            confidence = 0.95 if "contains nan" in message or "missing values" in message else 0.90
            return self._result(
                "data_quality",
                confidence,
                "Invalid, missing, non-finite, or incompatible feature values detected.",
            )

        if exception_type == "InvalidParameterError" or self._matches(
            self._CONFIG_PATTERNS, message
        ):
            confidence = 0.97 if "invalid parameter" in message or ("parameter" in message and "must be" in message) else 0.95
            return self._result(
                "configuration_error",
                confidence,
                "Invalid model or pipeline configuration detected from exception evidence.",
            )

        return self._result(
            "unknown_runtime_failure",
            0.40,
            "Runtime failure detected, but evidence does not support a known family.",
        )
