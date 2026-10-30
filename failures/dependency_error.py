from .base import FailureInjector


class DependencyErrorInjector(FailureInjector):
    name = "dependency_error"

    def inject(self, x, config):
        module = config["failures"]["dependency_error"]["module"]

        raise ModuleNotFoundError(
            f"No module named '{module}'"
        )