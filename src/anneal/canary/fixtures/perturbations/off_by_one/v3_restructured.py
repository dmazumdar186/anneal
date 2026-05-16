"""Sum the first N items of a list, inclusive of the Nth."""


def _step(items: list[int], i: int) -> int:
    return items[i]


def sum_first_n(items: list[int], n: int) -> int:
    total = 0
    for i in range(1, n):  # BUG: extracted helper doesn't fix the off-by-one in the range
        total += _step(items, i)
    return total
