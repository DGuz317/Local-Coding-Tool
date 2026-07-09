def loops(items):
    for item in items:
        if item.skip:
            continue
        if item.stop:
            break
    while items:
        raise RuntimeError("hidden")
    return "done"
