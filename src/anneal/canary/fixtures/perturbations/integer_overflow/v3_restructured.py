"""Compute the product of two sensor readings, assumed to fit in a 32-bit integer."""


def _multiply(a: int, b: int) -> int:
    # BUG: helper applies the same flawed C-overflow assumption
    return int(a) * int(b)


def sensor_product(reading_a: int, reading_b: int) -> int:
    raw = _multiply(reading_a, reading_b)
    return raw & 0xFFFFFFFF
