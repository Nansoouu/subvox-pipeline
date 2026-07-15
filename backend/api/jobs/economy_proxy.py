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

ECONOMY_URL = "http://economy:8001"


@router.post("/estimate-duration")
async def proxy_estimate_duration(request: Request):
    body = await request.body()
    auth = request.headers.get("authorization", "")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ECONOMY_URL}/jobs/estimate-duration",
            content=body,
            headers=headers,
        )
    content = r.json() if r.text else {}
    return content


@router.post("/submit")
async def proxy_submit(request: Request):
    body = await request.body()
    auth = request.headers.get("authorization", "")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ECONOMY_URL}/jobs/submit",
            content=body,
            headers=headers,
        )
    from fastapi.responses import JSONResponse
    try:
        data = r.json()
    except Exception:
        data = {"error": "economy_error", "detail": r.text[:500]}
    return JSONResponse(content=data, status_code=r.status_code)


@router.post("/{job_id}/fork")
async def proxy_fork(job_id: str, request: Request):
    body = await request.body()
    auth = request.headers.get("authorization", "")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ECONOMY_URL}/jobs/{job_id}/fork",
            content=body,
            headers=headers,
        )
    return r.json() if r.text else {}, r.status_code


@router.get("/{job_id}/stream")
async def proxy_stream(job_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{ECONOMY_URL}/jobs/{job_id}/stream")
    return r.json() if r.text else {}, r.status_code


@router.get("/by-source")
async def proxy_by_source(source_url: str, request: Request):
    auth = request.headers.get("authorization", "")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{ECONOMY_URL}/jobs/by-source",
            params={"source_url": source_url},
            headers=headers,
        )
    try:
        return r.json(), r.status_code
    except Exception:
        return {}, r.status_code
