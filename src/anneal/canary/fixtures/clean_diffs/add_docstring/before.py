import hashlib


def hash_password(password: str, salt: str) -> str:
    combined = salt + password
    return hashlib.sha256(combined.encode()).hexdigest()
