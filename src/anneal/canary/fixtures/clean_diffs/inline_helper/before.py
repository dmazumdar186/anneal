"""Clamp a value to the range [lo, hi]."""


def _clamp_value(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def clamp(value: float, low: float, high: float) -> float:
    return _clamp_value(value, low, high)
