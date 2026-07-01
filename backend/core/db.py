"""
core/db.py — Pool de connexions PostgreSQL async (asyncpg) — Subvox
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from core.config import settings
from core.logging_setup import get_logger

logger = get_logger(__name__)

_pool: asyncpg.Pool | None = None


def safe_uuid(val: str | None):
    """Convert to UUID if valid, else return None (for wallet addresses)."""
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


async def init_pool() -> None:
    global _pool
    dsn = settings.DATABASE_URL_POOLER or settings.DATABASE_URL
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,
    )
    logger.info("Pool asyncpg initialisé")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Pool asyncpg fermé")


@asynccontextmanager
async def get_conn() -> AsyncIterator[asyncpg.Connection]:
    """Récupère une connexion du pool (context manager)."""
    if _pool is None:
        raise RuntimeError("Pool DB non initialisé")
    async with _pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def direct_connect() -> AsyncIterator[asyncpg.Connection]:
    """Connexion directe (sans pool) — utilisée par les tasks Celery."""
    dsn = settings.DATABASE_URL_POOLER or settings.DATABASE_URL
    conn = await asyncpg.connect(dsn=dsn, timeout=10, statement_cache_size=0)
    try:
        yield conn
    finally:
        await conn.close()


async def fetchrow(query: str, *args):
    """Raccourci pour fetchrow."""
    async with get_conn() as conn:
        return await conn.fetchrow(query, *args)


async def fetch(query: str, *args):
    """Raccourci pour fetch."""
    async with get_conn() as conn:
        return await conn.fetch(query, *args)


async def execute(query: str, *args):
    """Raccourci pour execute."""
    async with get_conn() as conn:
        return await conn.execute(query, *args)


async def get_pool() -> asyncpg.Pool:
    """Retourne le pool de connexions (doit être initialisé)."""
    if _pool is None:
        raise RuntimeError("Pool DB non initialisé")
    return _pool
