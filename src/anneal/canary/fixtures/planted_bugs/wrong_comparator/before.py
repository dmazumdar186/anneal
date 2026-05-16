"""Check whether a computed status code matches the expected sentinel value."""


def is_sentinel(value: int, sentinel: int = 256) -> bool:
    # BUG: `is` tests object identity, not equality.
    # Works for small ints (CPython caches -5..256), silently breaks for larger values.
    return value is sentinel
