"""Convert a list of key-value tuples to a dictionary."""


def tuples_to_dict(pairs: list[tuple[str, str]]) -> dict[str, str]:
    result = {}
    for k, v in pairs:
        result[k] = v
    return result
