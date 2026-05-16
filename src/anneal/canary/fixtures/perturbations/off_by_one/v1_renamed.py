"""Accumulate values from the beginning of a sequence up to a given cutoff."""


def accumulate_to_count(data_array: list[int], cutoff: int) -> int:
    running_total = 0
    for idx in range(1, cutoff):  # BUG: same off-by-one — starts at 1, misses index 0
        running_total += data_array[idx]
    return running_total
