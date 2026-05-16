"""Sum the first N items of a list, inclusive of the Nth."""


def sum_first_n(
    items: list[int],
    n: int,
) -> int:
    # accumulate over the first n elements
    total = 0
    for i in range(
        1,  # BUG: starts at 1 instead of 0
        n,
    ):
        total += items[i]
    return total
