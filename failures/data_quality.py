import numpy as np

from .base import FailureInjector


class DataQualityInjector(FailureInjector):
    name = "data_quality"

    def inject(self, x, config):
        column = config["failures"]["data_quality"]["column"]
        fraction = config["failures"]["data_quality"]["missing_fraction"]

        if column not in x.columns:
            raise KeyError(f"Column '{column}' not found.")

        x = x.copy()

        n = max(1, int(len(x) * fraction))

        seed = config["failures"]["data_quality"].get(
            "random_seed", 42
        )

        rng = np.random.default_rng(seed)

        idx = rng.choice(
            x.index,
            size=n,
            replace=False
        )

        x.loc[idx, column] = np.nan

        return x