"""Sum the first N items of a list, inclusive of the Nth."""


def sum_first_n(items: list[int], n: int) -> int:
    total = 0
    for i in range(1, n):  # BUG: should be range(n) — starts at 1 instead of 0
        total += items[i]
    return total
