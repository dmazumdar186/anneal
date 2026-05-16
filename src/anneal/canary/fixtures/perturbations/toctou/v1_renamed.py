"""Create a lock file only if no lock file is currently present."""
import os


def acquire_lock(lock_path: str, owner: str) -> None:
    # BUG: same TOCTOU — exists() check then open() is not atomic
    if not os.path.exists(lock_path):
        with open(lock_path, "w") as fh:
            fh.write(owner)
