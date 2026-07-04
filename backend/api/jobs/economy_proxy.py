"""
api/jobs/economy_proxy.py — Proxy routes that forward to Economy (port 8001).

These endpoints live in the Economy service but are called by the frontend
via the Pipeline API URL. We proxy them to avoid CORS/URL mismatches.
"""

import httpx
from fastapi import APIRouter, Request
from core.logging_setup import get_logger

router = APIRouter()
logger = get_logger(__name__)

ECONOMY_URL = "http://127.0.0.1:8001"


@router.post("/estimate-duration")
async def proxy_estimate_duration(request: Request):
    body = await request.body()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ECONOMY_URL}/jobs/estimate-duration",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return r.json() if r.text else {}, r.status_code


@router.post("/submit")
async def proxy_submit(request: Request):
    body = await request.body()
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ECONOMY_URL}/jobs/submit",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return r.json() if r.text else {}, r.status_code
