def is_configuration_failure(exception):
    message = str(exception).lower()
    exception_type = type(exception).__name__

    return (
        exception_type == "InvalidParameterError"
        or "invalid parameter" in message
        or (
            "parameter" in message
            and "must be" in message
        )
    )