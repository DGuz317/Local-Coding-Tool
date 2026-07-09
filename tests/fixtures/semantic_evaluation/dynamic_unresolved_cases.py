# ruff: noqa: F403, F405
from plugin import *


def uncertain(value):
    global dynamic_name
    if check(value):
        return missing_name
    try:
        with value:
            return value
    except ValueError:
        return fallback
    match value:
        case 3:
            return value
