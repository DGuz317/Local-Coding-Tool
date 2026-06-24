from auth.login import login_timeout_handler


def test_login_timeout_handler() -> None:
    assert login_timeout_handler("demo") == 30
