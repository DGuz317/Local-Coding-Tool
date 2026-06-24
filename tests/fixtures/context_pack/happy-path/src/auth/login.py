from auth.session import timeout_seconds


def login_timeout_handler(user_id: str) -> int:
    return timeout_seconds(user_id)
