"""Combine two telemetry readings into a 32-bit bounded measurement."""


def combine_telemetry(channel_a: int, channel_b: int) -> int:
    # BUG: same overflow-assumption smell — Python ints are unbounded
    combined = int(channel_a) * int(channel_b)
    return combined & 0xFFFFFFFF
