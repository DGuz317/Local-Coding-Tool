from dogpkg.util import normalize


def build_message(name: str) -> str:
    return f"hello {normalize(name)}"
