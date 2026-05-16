"""Parse a CSV file and return the first non-header row as a dict."""
import csv
from typing import Optional


def read_first_row(
    filepath: str,
) -> Optional[dict]:
    f = open(  # BUG: no `with` — file not closed on early return
        filepath,
        newline="",
        encoding="utf-8",
    )
    reader = csv.DictReader(f)

    for row in reader:
        return dict(row)

    return None
