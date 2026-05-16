"""Check whether a computed status code matches the expected sentinel value."""


def is_sentinel(
    value: int,
    sentinel: int = 256,
) -> bool:
    # compare value against the sentinel
    result = (
        value is sentinel  # BUG: identity not equality; fragile outside small-int cache
    )
    return result
