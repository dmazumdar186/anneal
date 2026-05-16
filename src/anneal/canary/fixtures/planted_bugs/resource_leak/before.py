"""Parse a CSV file and return the first non-header row as a dict."""
import csv
from typing import Optional


def read_first_row(filepath: str) -> Optional[dict]:
    # BUG: if the file is empty (no data rows), we return None without closing the file handle.
    f = open(filepath, newline="", encoding="utf-8")
    reader = csv.DictReader(f)
    for row in reader:
        return dict(row)  # early return leaks the file handle
    return None
