def is_data_quality_failure(exception):
    message = str(exception).lower()

    return (
        "contains nan" in message
        or "missing values" in message
        or "nan" in message
        or "infinity" in message
    )