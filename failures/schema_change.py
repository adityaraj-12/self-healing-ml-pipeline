from .base import FailureInjector


class SchemaChangeInjector(FailureInjector):
    name = "schema_change"

    def inject(self, x, config):
        old = config["failures"]["schema_change"]["original_column"]
        new = config["failures"]["schema_change"]["replacement_column"]

        if old not in x.columns:
            raise KeyError(f"Column '{old}' not found for schema injection.")

        x = x.rename(columns={old: new})

        return x