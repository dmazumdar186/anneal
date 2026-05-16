"""Parse a CSV file and return the first non-header row as a dict."""
import csv
from typing import Optional


def _open_csv_reader(filepath: str):
    # BUG: returns an open file handle and reader; caller never closes the handle
    f = open(filepath, newline="", encoding="utf-8")
    return f, csv.DictReader(f)


def read_first_row(filepath: str) -> Optional[dict]:
    _file, reader = _open_csv_reader(filepath)
    for row in reader:
        return dict(row)  # _file is never closed here
    return None
