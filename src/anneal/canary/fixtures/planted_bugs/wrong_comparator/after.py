"""Check whether a computed status code matches the expected sentinel value."""


def is_sentinel(value: int, sentinel: int = 256) -> bool:
    # FIX: use == for value equality, not `is` for identity.
    # CPython caches small ints (-5..256), so `is` accidentally works for the default
    # sentinel=256 but silently breaks for any value outside that range.
    return value == sentinel
