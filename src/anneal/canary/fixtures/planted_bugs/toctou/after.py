"""Write data to a file only if the file does not already exist (safe-write helper)."""


def safe_write(path: str, data: str) -> None:
    # FIX: open with exclusive-creation flag "x" — atomic at the OS level, raises
    # FileExistsError if another process already created the file.
    try:
        with open(path, "x") as f:
            f.write(data)
    except FileExistsError:
        pass  # file already exists — no action needed, consistent with original intent
