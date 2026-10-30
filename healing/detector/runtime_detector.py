def is_dependency_failure(exception):
    exception_type = type(exception).__name__
    message = str(exception).lower()

    return (
        exception_type in {
            "ModuleNotFoundError",
            "ImportError"
        }
        or "no module named" in message
        or "dependency" in message
    )