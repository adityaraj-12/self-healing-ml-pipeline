from .base import FailureInjector


class ConfigurationErrorInjector(FailureInjector):
    name = "configuration_error"

    def inject(self, x, config):
        config = config.copy()

        parameter = config["failures"]["configuration_error"]["parameter"]
        value = config["failures"]["configuration_error"]["invalid_value"]

        config["model"][parameter] = value

        return x, config