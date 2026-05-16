"""Parse a CSV file and return the first non-header row as a dict."""
import csv
from typing import Optional


def read_first_row(filepath: str) -> Optional[dict]:
    # FIX: use `with` statement so the file is always closed, even on early return.
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            return dict(row)
    return None
