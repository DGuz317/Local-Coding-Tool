DEFAULT_TIMEOUT_SECONDS = 30


def timeout_seconds(user_id: str) -> int:
    if user_id:
        return DEFAULT_TIMEOUT_SECONDS
    return 0
