"""Compute the product of two sensor readings, assumed to fit in a 32-bit integer."""

_MASK = 0xFFFFFFFF


def sensor_product(reading_a: int, reading_b: int) -> int:
    # multiply the two readings
    result = (
        int(reading_a)
        * int(reading_b)  # BUG: C-style overflow assumption; Python int never overflows
    )

    # truncate to 32 bits
    return result & _MASK
