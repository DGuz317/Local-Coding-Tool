from auth.session import timeout_seconds


def test_timeout_seconds() -> None:
    assert timeout_seconds("demo") == 30
