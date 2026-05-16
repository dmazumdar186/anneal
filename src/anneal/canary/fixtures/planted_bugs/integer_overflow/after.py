"""Compute the product of two sensor readings as a true 32-bit unsigned value."""


def sensor_product(reading_a: int, reading_b: int) -> int:
    # FIX: document explicitly that the 32-bit mask is intentional wrapping behaviour,
    # not a guard against overflow. Python ints never overflow; the mask is the contract.
    result = reading_a * reading_b
    # Explicit 32-bit unsigned wrap — this IS the intended semantic, not overflow protection.
    return result & 0xFFFFFFFF
