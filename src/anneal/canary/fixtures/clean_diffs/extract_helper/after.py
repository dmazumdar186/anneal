"""Compute the Euclidean distance between two 2D points."""
import math


def _squared_diff(a: float, b: float) -> float:
    return (b - a) ** 2


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt(_squared_diff(x1, x2) + _squared_diff(y1, y2))
