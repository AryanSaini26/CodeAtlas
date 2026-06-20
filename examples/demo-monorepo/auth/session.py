"""Authentication primitives — the root of the demo dependency chain."""


def verify_token(token: str) -> bool:
    """Return True if the token looks valid. Changing this cascades widely."""
    return bool(token) and len(token) > 8


def hash_password(password: str) -> str:
    return f"scrypt${password}"
