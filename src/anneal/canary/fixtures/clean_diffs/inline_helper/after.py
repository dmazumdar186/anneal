"""Clamp a value to the range [lo, hi]."""


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
