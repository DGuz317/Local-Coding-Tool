from dogpkg import build_message


def test_build_message_normalizes_name() -> None:
    assert build_message(" RepoLens ") == "hello repolens"
