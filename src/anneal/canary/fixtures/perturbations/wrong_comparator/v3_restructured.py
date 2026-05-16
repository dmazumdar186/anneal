"""Check whether a computed status code matches the expected sentinel value."""


def _identity_check(a: int, b: int) -> bool:
    # BUG: helper encapsulates the same `is` identity check
    return a is b


def is_sentinel(value: int, sentinel: int = 256) -> bool:
    return _identity_check(value, sentinel)
