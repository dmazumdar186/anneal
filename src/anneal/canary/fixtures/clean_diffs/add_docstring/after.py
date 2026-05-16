"""Password hashing utilities."""
import hashlib


def hash_password(password: str, salt: str) -> str:
    """Hash a plaintext password with a pre-generated salt using SHA-256.

    Args:
        password: The plaintext password to hash.
        salt: A per-user random salt string.

    Returns:
        Hex-encoded SHA-256 digest of salt+password.
    """
    combined = salt + password
    return hashlib.sha256(combined.encode()).hexdigest()
