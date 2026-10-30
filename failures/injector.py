from .schema_change import SchemaChangeInjector
from .data_quality import DataQualityInjector
from .configuration_error import ConfigurationErrorInjector
from .dependency_error import DependencyErrorInjector


INJECTORS = {
    "schema_change": SchemaChangeInjector(),
    "data_quality": DataQualityInjector(),
    "configuration_error": ConfigurationErrorInjector(),
    "dependency_error": DependencyErrorInjector(),
}


def inject_failure(failure_type, x, config):
    if failure_type not in INJECTORS:
        raise ValueError(
            f"Unknown failure type: {failure_type}"
        )

    injector = INJECTORS[failure_type]

    result = injector.inject(x, config)

    if isinstance(result, tuple):
        return result

    return result, config