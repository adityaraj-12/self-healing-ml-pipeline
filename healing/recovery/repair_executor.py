from copy import deepcopy
import math

import pandas as pd
from pandas.api.types import is_numeric_dtype


class RepairExecutor:
    """
    Executes only predefined, allowlisted repair actions.
    Never executes arbitrary LLM-generated Python or shell commands.
    """

    def apply_schema_repair(self, x, candidate):
        if candidate["action"] != "rename_column":
            raise ValueError(
                "Unsupported schema repair action."
            )

        mapping = candidate["parameters"].get(
            "column_mapping", {}
        )

        if not mapping:
            raise ValueError("Empty schema mapping.")

        for source, target in mapping.items():
            if source not in x.columns:
                raise ValueError(
                    f"Source column not found: {source}"
                )

            if target in x.columns:
                raise ValueError(
                    f"Target column already exists: {target}"
                )

        repaired = x.copy(deep=True).rename(
            columns=mapping,
            errors="raise"
        )

        return repaired

    def apply_configuration_repair(
        self, config, candidate
    ):
        if candidate["action"] != "restore_configuration":
            raise ValueError(
                "Unsupported configuration repair action."
            )

        repaired = deepcopy(config)
        changes = candidate["parameters"].get(
            "changes", []
        )

        if not changes:
            raise ValueError(
                "No configuration changes were proposed."
            )

        
        allowed_parameters = {"C", "max_iter"}

        for change in changes:
            parameter = change["parameter"]
            expected = change["observed_value"]
            proposed = change["proposed_value"]

            if parameter not in allowed_parameters:
                raise ValueError(
                    f"Unsupported configuration parameter: {parameter}"
                )

            if parameter == "C":
                valid_value = (
                    isinstance(proposed, (int, float))
                    and not isinstance(proposed, bool)
                    and math.isfinite(proposed)
                    and proposed > 0
                )

                if not valid_value:
                    raise ValueError(
                        "C must be finite and positive."
                    )

            elif parameter == "max_iter":
                valid_value = (
                    isinstance(proposed, int)
                    and not isinstance(proposed, bool)
                    and proposed >= 1
                )

                if not valid_value:
                    raise ValueError(
                        "max_iter must be a positive integer."
                    )

            actual = repaired["model"].get(parameter)

            if actual != expected:
                raise ValueError(
                    f"Configuration changed unexpectedly: {parameter}"
                )

            repaired["model"][parameter] = proposed


        # Check constraints relevant to our current model.
        model_config = repaired["model"]

        if model_config.get("C", 0) <= 0:
            raise ValueError(
                "LogisticRegression C must be positive."
            )

        if model_config.get("max_iter", 0) < 1:
            raise ValueError(
                "max_iter must be at least 1."
            )

        return repaired

    def impute_training_test(
        self, x_train, x_test, candidate
    ):
        if candidate["action"] != "impute_missing_values":
            raise ValueError(
                "Unsupported data-quality repair action."
            )

        train = x_train.copy(deep=True)
        test = x_test.copy(deep=True)

        for column in train.columns:
            has_missing = (
                train[column].isna().any()
                or test[column].isna().any()
            )

            if not has_missing:
                continue

            # Fit imputation values on training data only. Reject a
            # completely missing training column before calculating a median,
            # which otherwise emits a NumPy RuntimeWarning before failing.
            if is_numeric_dtype(train[column]):
                observed_training_values = train[column].dropna()
                if observed_training_values.empty:
                    raise ValueError(
                        f"No valid training imputation value for {column}"
                    )
                fill_value = observed_training_values.median()
            else:
                modes = train[column].mode(dropna=True)

                if modes.empty:
                    raise ValueError(
                        f"Cannot impute column {column}"
                    )

                fill_value = modes.iloc[0]

            if pd.isna(fill_value):
                raise ValueError(
                    f"No valid training imputation value "
                    f"for {column}"
                )

            train[column] = train[column].fillna(fill_value)
            test[column] = test[column].fillna(fill_value)

        if train.isna().any().any() or test.isna().any().any():
            raise ValueError(
                "Missing values remain after imputation."
            )

        return train, test