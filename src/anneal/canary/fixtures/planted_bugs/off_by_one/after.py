"""Sum the first N items of a list, inclusive of the Nth."""


def sum_first_n(items: list[int], n: int) -> int:
    total = 0
    # FIX: range(n) starts at 0 and runs through index n-1, covering all N items.
    for i in range(n):
        total += items[i]
    return total
