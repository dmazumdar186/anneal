"""Write data to a file only if the file does not already exist (safe-write helper)."""
import os


def safe_write(path: str, data: str) -> None:
    # BUG: TOCTOU — another process can create the file between the exists() check and open().
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(data)
