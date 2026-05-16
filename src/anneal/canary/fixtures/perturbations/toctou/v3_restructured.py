"""Write data to a file only if the file does not already exist (safe-write helper)."""
import os


def _file_is_absent(path: str) -> bool:
    return not os.path.exists(path)


def safe_write(path: str, data: str) -> None:
    # BUG: extracting the check into a helper doesn't help — the race window remains
    if _file_is_absent(path):
        with open(path, "w") as f:
            f.write(data)
