"""Compute basic statistics for a list of numbers."""


def mean(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values):
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return sum((x - avg) ** 2 for x in values) / (len(values) - 1)
