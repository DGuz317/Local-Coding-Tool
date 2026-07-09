# ruff: noqa: E731, F821, F841
GLOBAL = 1


def outer(value):
    shared = value
    items = [shared + value for shared in range(3)]
    mapper = lambda item: item + shared

    def inner(shared):
        nonlocal value
        global GLOBAL
        missing = shared + value + GLOBAL + unknown
        return missing

    return mapper
