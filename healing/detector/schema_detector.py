def is_schema_failure(exception):
    message = str(exception).lower()

    return (
        "schema mismatch" in message
        or "missing" in message and "unexpected" in message
        or "column" in message and "not found" in message
        or type(exception).__name__ == "KeyError"
    )