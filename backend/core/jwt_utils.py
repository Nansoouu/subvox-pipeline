"""core/jwt_utils.py — JWT token creation and verification for Subvox."""

import time
import jwt
from core.config import settings

SECRET = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM


def create_access_token(user_id: str, email: str = "", role: str = "user") -> str:
    """Create a JWT access token for a wallet-authenticated user."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email or user_id,
        "role": role,
        "iat": now,
        "exp": now + settings.JWT_EXPIRATION_HOURS * 3600,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns payload or None if invalid."""
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
