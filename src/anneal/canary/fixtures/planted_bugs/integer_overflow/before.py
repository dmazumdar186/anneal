"""Compute the product of two sensor readings, assumed to fit in a 32-bit integer."""


def sensor_product(reading_a: int, reading_b: int) -> int:
    # BUG: author assumes C-style 32-bit overflow semantics.
    # Python ints are arbitrary precision — the result silently grows instead of wrapping.
    # Downstream code that masks with 0xFFFFFFFF will behave differently than expected.
    result = int(reading_a) * int(reading_b)
    return result & 0xFFFFFFFF  # misleadingly correct but hides the wrong mental model
