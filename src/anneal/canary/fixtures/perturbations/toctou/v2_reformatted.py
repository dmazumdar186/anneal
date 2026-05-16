"""Write data to a file only if the file does not already exist (safe-write helper)."""
import os


def safe_write(path: str, data: str) -> None:
    # check first, then write — NOT atomic
    file_exists = os.path.exists(path)

    if not file_exists:
        # BUG: another process may have created the file between the check above and now
        with open(path, "w") as f:
            f.write(data)
