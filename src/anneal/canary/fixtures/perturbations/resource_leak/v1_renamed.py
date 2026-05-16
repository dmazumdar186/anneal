"""Read the first log entry from a TSV audit log and return it as a dictionary."""
import csv
from typing import Optional


def read_first_log_entry(log_path: str) -> Optional[dict]:
    # BUG: same resource leak — handle opened without `with`, early return skips close
    handle = open(log_path, newline="", encoding="utf-8")
    reader = csv.DictReader(handle, delimiter="\t")
    for entry in reader:
        return dict(entry)
    return None
