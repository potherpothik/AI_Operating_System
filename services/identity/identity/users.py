from pathlib import Path

import bcrypt
import yaml

_USERS_FILE = Path(__file__).parent / "users.yaml"


def _load_users() -> list[dict]:
    data = yaml.safe_load(_USERS_FILE.read_text()) or {}
    return data.get("users", [])


def authenticate(username: str, password: str) -> dict | None:
    """Real bcrypt verification against the real password hash on file —
    returns the real user record on success, None on any mismatch.
    Constant-time comparison is bcrypt's own guarantee, not something
    this function has to implement itself."""
    for user in _load_users():
        if user["username"] == username:
            if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                return user
            return None
    return None


def get_by_sub(sub: str) -> dict | None:
    for user in _load_users():
        if user["sub"] == sub:
            return user
    return None
