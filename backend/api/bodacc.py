"""
api/bodacc.py — BODACC subscription endpoint.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.db import _pool as pool

router = APIRouter(prefix="/bodacc", tags=["bodacc"])


class SubscribeRequest(BaseModel):
    email: str


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    if not req.email or "@" not in req.email:
        raise HTTPException(400, "Email invalide")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bodacc_subscribers (email) VALUES ($1) ON CONFLICT (email) DO NOTHING",
            req.email,
        )
    return {"ok": True}
