"""
api/auth_router.py — Authentication endpoints for Pipeline.
Handles: email/password, Google OAuth, GitHub OAuth, X OAuth.
"""

import secrets
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from passlib.hash import bcrypt
from core.db import _pool as pool
from core.jwt_utils import create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth config from .env ───────────────────────────────────────────
from core.config import settings

GOOGLE_CLIENT_ID = getattr(settings, "GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = getattr(settings, "GOOGLE_REDIRECT_URI", "https://api.subvox.xyz/auth/google/callback")

GITHUB_CLIENT_ID = getattr(settings, "GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = getattr(settings, "GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = getattr(settings, "GITHUB_REDIRECT_URI", "https://api.subvox.xyz/auth/github/callback")

TWITTER_CLIENT_ID = getattr(settings, "TWITTER_CLIENT_ID", "")
TWITTER_CLIENT_SECRET = getattr(settings, "TWITTER_CLIENT_SECRET", "")
TWITTER_REDIRECT_URI = getattr(settings, "TWITTER_REDIRECT_URI", "https://api.subvox.xyz/auth/twitter/callback")

FRONTEND_URL = getattr(settings, "FRONTEND_URL", "https://subvox.xyz")


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_user_by_email(email: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
    return row

async def _get_user_by_provider(provider: str, provider_id: str):
    col = {"google": "google_id", "github": "github_id", "x": "x_id"}.get(provider)
    if not col:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT * FROM users WHERE {col} = $1", provider_id)
    return row

async def _create_user(email: str, name: str = "", provider: str = "", provider_id: str = "", avatar_url: str = ""):
    uid = f"sub_{secrets.token_hex(12)}"
    cols = ["id", "email", "name", "role", "avatar_url"]
    vals = [uid, email, name, "user", avatar_url]
    placeholders = ["$1", "$2", "$3", "$4", "$5"]

    if provider and provider_id:
        col_map = {"google": "google_id", "github": "github_id", "x": "x_id"}
        col = col_map.get(provider)
        if col:
            cols.append(col)
            vals.append(provider_id)
            placeholders.append(f"${len(vals)}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *",
            *vals
        )
    return row

async def _ensure_subscription(user_id: str):
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM subscriptions WHERE user_id = $1", user_id)
        if not exists:
            await conn.execute("INSERT INTO subscriptions (user_id, plan, tier) VALUES ($1, 'decouverte', 'decouverte')", user_id)


# ── Email / Password ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""

@router.post("/login")
async def login(req: LoginRequest):
    user = await _get_user_by_email(req.email)
    if not user:
        raise HTTPException(401, "Email ou mot de passe incorrect")
    if not user["password_hash"]:
        raise HTTPException(401, "Ce compte utilise OAuth, pas de mot de passe")
    if not bcrypt.verify(req.password, user["password_hash"]):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    token = create_access_token(user["id"], user["email"], user["role"])
    await _ensure_subscription(user["id"])
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_login = NOW() WHERE id = $1", user["id"])
    return {"access_token": token, "token_type": "bearer", "user": {"id": user["id"], "email": user["email"], "name": user.get("name", ""), "role": user["role"]}}

@router.post("/register")
async def register(req: RegisterRequest):
    existing = await _get_user_by_email(req.email)
    if existing:
        raise HTTPException(409, "Cet email est déjà utilisé")
    uid = f"sub_{secrets.token_hex(12)}"
    pw_hash = bcrypt.hash(req.password)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, name, password_hash, role) VALUES ($1, $2, $3, $4, 'user')",
            uid, req.email, req.name or "", pw_hash
        )
    await _ensure_subscription(uid)
    token = create_access_token(uid, req.email, "user")
    return {"access_token": token, "token_type": "bearer", "user": {"id": uid, "email": req.email, "name": req.name, "role": "user"}}


# ── Google OAuth ────────────────────────────────────────────────────

@router.get("/google/login")
async def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google OAuth not configured")
    state = secrets.token_urlsafe(16)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        f"&state={state}"
        "&access_type=offline"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)

@router.get("/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"Google OAuth error: {error}")
    async with httpx.AsyncClient() as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        })
        if r.status_code != 200:
            raise HTTPException(400, "Failed to exchange Google code")
        tokens = r.json()
        r2 = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"})
        if r2.status_code != 200:
            raise HTTPException(400, "Failed to get Google user info")
        info = r2.json()

    email = info.get("email", "")
    google_id = info.get("id", "")
    name = info.get("name", "")
    avatar = info.get("picture", "")

    user = await _get_user_by_provider("google", google_id)
    if not user:
        user = await _get_user_by_email(email)
        if user:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE users SET google_id = $1, avatar_url = $2 WHERE id = $3", google_id, avatar, user["id"])
        else:
            user = await _create_user(email, name, "google", google_id, avatar)

    await _ensure_subscription(user["id"])
    token = create_access_token(user["id"], user["email"], user["role"])
    from fastapi.responses import RedirectResponse
    return RedirectResponse(_oauth_redirect(token))

def _oauth_redirect(token: str):
    return f"{FRONTEND_URL}/app?token={token}"


# ── GitHub OAuth ────────────────────────────────────────────────────

@router.get("/github/login")
async def github_login():
    if not GITHUB_CLIENT_ID:
        raise HTTPException(503, "GitHub OAuth not configured")
    state = secrets.token_urlsafe(16)
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&state={state}"
        "&scope=read:user%20user:email"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)

@router.get("/github/callback")
async def github_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"GitHub OAuth error: {error}")
    async with httpx.AsyncClient() as client:
        r = await client.post("https://github.com/login/oauth/access_token", data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        }, headers={"Accept": "application/json"})
        if r.status_code != 200:
            raise HTTPException(400, "Failed to exchange GitHub code")
        tokens = r.json()
        r2 = await client.get("https://api.github.com/user",
            headers={"Authorization": f"Bearer {tokens['access_token']}"})
        if r2.status_code != 200:
            raise HTTPException(400, "Failed to get GitHub user info")
        info = r2.json()
        r3 = await client.get("https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {tokens['access_token']}"})
        emails = r3.json() if r3.status_code == 200 else []
        primary = next((e["email"] for e in emails if e.get("primary")), info.get("email", ""))

    github_id = str(info.get("id", ""))
    email = primary or f"github_{github_id}"
    name = info.get("name") or info.get("login", "")
    avatar = info.get("avatar_url", "")

    user = await _get_user_by_provider("github", github_id)
    if not user:
        user = await _get_user_by_email(email)
        if user:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE users SET github_id = $1, avatar_url = $2 WHERE id = $3", github_id, avatar, user["id"])
        else:
            user = await _create_user(email, name, "github", github_id, avatar)

    await _ensure_subscription(user["id"])
    token = create_access_token(user["id"], user["email"], user["role"])
    from fastapi.responses import RedirectResponse
    return RedirectResponse(_oauth_redirect(token))


# ── X (Twitter) OAuth 2.0 ───────────────────────────────────────────

@router.get("/twitter/login")
async def twitter_login():
    if not TWITTER_CLIENT_ID:
        raise HTTPException(503, "X OAuth not configured")
    state = secrets.token_urlsafe(16)
    url = (
        "https://twitter.com/i/oauth2/authorize"
        f"?client_id={TWITTER_CLIENT_ID}"
        f"&redirect_uri={TWITTER_REDIRECT_URI}"
        "&response_type=code"
        f"&state={state}"
        "&scope=tweet.read%20users.read"
        "&code_challenge=challenge"
        "&code_challenge_method=plain"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)

@router.get("/twitter/callback")
async def twitter_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"X OAuth error: {error}")
    async with httpx.AsyncClient() as client:
        r = await client.post("https://api.twitter.com/2/oauth2/token", data={
            "client_id": TWITTER_CLIENT_ID,
            "client_secret": TWITTER_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": TWITTER_REDIRECT_URI,
            "code_verifier": "challenge",
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            raise HTTPException(400, "Failed to exchange X code")
        tokens = r.json()
        r2 = await client.get("https://api.twitter.com/2/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"})
        if r2.status_code != 200:
            raise HTTPException(400, "Failed to get X user info")
        info = r2.json().get("data", {})

    x_id = info.get("id", "")
    name = info.get("name", "")
    username = info.get("username", "")

    user = await _get_user_by_provider("x", x_id)
    if not user:
        user = await _create_user(f"x_{x_id}", name or username, "x", x_id, "")

    await _ensure_subscription(user["id"])
    token = create_access_token(user["id"], user["email"], user["role"])
    from fastapi.responses import RedirectResponse
    return RedirectResponse(_oauth_redirect(token))


# ── /me ─────────────────────────────────────────────────────────────

@router.get("/me")
async def me(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Non authentifié")
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(401, "Token invalide")
    user_id = payload.get("sub")
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, email, name, role, avatar_url FROM users WHERE id = $1", user_id)
        sub = await conn.fetchrow("SELECT * FROM subscriptions WHERE user_id = $1", user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    return {
        "id": user["id"],
        "email": user["email"] or "",
        "name": user.get("name", ""),
        "role": user["role"],
        "avatar_url": user.get("avatar_url", ""),
        "subscription": {
            "plan": sub["plan"] if sub else "decouverte",
            "tier": sub["tier"] if sub else "decouverte",
            "period_end": sub.get("period_end").isoformat() if sub and sub.get("period_end") else None,
            "watermark_text": sub.get("watermark_text") if sub else "Subvox",
            "watermark_paid": sub.get("watermark_paid", False) if sub else False,
        } if sub else None,
    }
