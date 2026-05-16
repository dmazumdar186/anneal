"""Compute the Euclidean distance between two 2D points."""
import math


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
