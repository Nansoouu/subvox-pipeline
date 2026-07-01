"""
api/auth.py — Auth minimal pour Pipeline.
Vérifie les JWT générés par Economy (port 8001).
Ne gère PAS le login Phantom — c'est le rôle de Economy.
"""

from fastapi import Header, HTTPException
from core.jwt_utils import decode_token


async def get_current_user_optional(authorization: str = Header(None, alias="Authorization")):
    """Vérifie le JWT et retourne l'utilisateur ou None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    payload = decode_token(token)
    if payload is None:
        return None
    return {"id": payload.get("sub"), "role": payload.get("role", "user")}


async def get_current_user(authorization: str = Header(None, alias="Authorization")):
    """Vérifie le JWT et retourne l'utilisateur (obligatoire)."""
    user = await get_current_user_optional(authorization)
    if user is None:
        raise HTTPException(401, "Non authentifié")
    return user
