#!/usr/bin/env python3
"""
sync_platforms.py — Import toutes les plateformes supportées par yt-dlp dans la DB.

Usage:
    cd pipeline && PYTHONPATH=backend .venv/bin/python ../scripts/sync_platforms.py

Catégorise automatiquement chaque extracteur par type de contenu,
détecte les extracteurs cassés ("CURRENTLY BROKEN"),
et assigne un niveau d'importance.
"""

import asyncio
import re
import sys
from pathlib import Path

# Ajouter backend au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from core.db import init_pool, close_pool, get_conn

# ── Mapping extracteur → content_type ──────────────────────────────────
CONTENT_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(youtube|vimeo|dailymotion|twitch|bilibili|nicovideo|youku|tudou|sina|iqiyi|le\.tv|metacafe|veoh|break\.com)", re.I), "video"),
    (re.compile(r"(twitter|x\.com|tiktok|instagram|facebook|reddit|linkedin|pinterest|snapchat|telegram|whatsapp|weibo|tumblr|mastodon|bluesky|threads)", re.I), "social"),
    (re.compile(r"(soundcloud|bandcamp|spotify|deezer|apple.?music|audiomack|mixcloud|shazam|tidal|napster|beatport|musical\.ly)", re.I), "audio"),
    (re.compile(r"(live|stream|periscope|dlive|trovo|kick\.com)", re.I), "live"),
    (re.compile(r"(twitch|steam|epicgames|roblox|minecraft|speedrun|playlist)", re.I), "gaming"),
    (re.compile(r"(bbc|cnn|nbc|abc|fox|cbs|msnbc|euronews|aljazeera|france24|rt\.com|sky.?news|the.?guardian|washington.?post|nytimes|reuters|bloomberg|apnews|npr)", re.I), "news"),
    (re.compile(r"(udemy|coursera|khan.?academy|edx|ted\.com|brilliant|codecademy|pluralsight|lynda\.com)", re.I), "education"),
    # Si rien d'autre ne match, "video" par défaut
]

# ── Mapping slug → website (pour les plateformes connues) ──────────────
KNOWN_WEBSITES: dict[str, str] = {
    "youtube":     "https://youtube.com",
    "twitter":     "https://x.com",
    "tiktok":      "https://tiktok.com",
    "instagram":   "https://instagram.com",
    "vimeo":       "https://vimeo.com",
    "dailymotion": "https://dailymotion.com",
    "facebook":    "https://facebook.com",
    "twitch":      "https://twitch.tv",
    "reddit":      "https://reddit.com",
    "tumblr":      "https://tumblr.com",
    "linkedin":    "https://linkedin.com",
    "pinterest":   "https://pinterest.com",
    "snapchat":    "https://snapchat.com",
    "telegram":    "https://telegram.org",
    "whatsapp":    "https://whatsapp.com",
    "weibo":       "https://weibo.com",
    "soundcloud":  "https://soundcloud.com",
    "bandcamp":    "https://bandcamp.com",
    "spotify":     "https://spotify.com",
    "deezer":      "https://deezer.com",
    "steam":       "https://steamcommunity.com",
    "roblox":      "https://roblox.com",
    "bbc":         "https://bbc.co.uk",
    "cnn":         "https://cnn.com",
    "udemy":       "https://udemy.com",
    "coursera":    "https://coursera.org",
    "ted":         "https://ted.com",
    "bilibili":    "https://bilibili.com",
    "nicovideo":   "https://nicovideo.jp",
}

# ── Importance par catégorie (pour le tri) ────────────────────────────
IMPORTANCE_BY_CATEGORY: dict[str, int] = {
    "social": 100,
    "video":  90,
    "live":   80,
    "audio":  70,
    "news":   60,
    "education": 50,
    "gaming": 40,
    "adult":  10,
}

# ── Sites "adult" (peu nombreux, explicites) ─────────────────────────
ADULT_PATTERNS = re.compile(
    r"(porn|xxx|sex|onlyfans|fansly|xvideos|xnxx|redtube|youporn|pornhub|"
    r"xhamster|stripchat|chaturbate|cam4|camster|myfreecams|livejasmin)", re.I
)


def classify_extractor(name: str) -> str:
    """Détermine le content_type d'un extracteur par son nom."""
    # Check adult first
    if ADULT_PATTERNS.search(name):
        return "adult"

    for pattern, ctype in CONTENT_TYPE_RULES:
        if pattern.search(name):
            return ctype
    return "video"


def extract_slug(name: str) -> str:
    """Convertit un nom d'extracteur en slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:64]


def extract_base_name(name: str) -> str:
    """Extrait le nom de base (sans sous-extracteur)."""
    # "9gag" -> "9gag", "9gag:tag" -> "9gag"
    parts = name.split(":")
    return parts[0]


async def sync_platforms():
    """Parse la sortie de yt-dlp --list-extractors et remplit la table."""
    await init_pool()

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--list-extractors",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    raw_lines = stdout.decode().splitlines()

    # Parser les lignes
    extractors: dict[str, dict] = {}

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        is_broken = "CURRENTLY BROKEN" in line.upper()
        # Nettoyer le marqueur
        name = re.sub(r"\s*\(CURRENTLY BROKEN\)\s*", "", line, flags=re.I).strip()
        # Ignorer les sous-extracteurs (avec ":")
        # Mais on garde le premier niveau pour le nom d'affichage
        base_name = extract_base_name(name)
        if base_name not in extractors:
            extractors[base_name] = {
                "name": base_name,
                "slug": extract_slug(base_name),
                "status": "broken" if is_broken else "active",
                "is_broken": is_broken,
            }

    print(f"📦 {len(extractors)} extracteurs uniques trouvés")

    # Insérer dans la DB
    inserted = 0
    updated = 0
    skipped = 0

    for slug, info in extractors.items():
        # Vérifier si le slug existe déjà
        async with get_conn() as conn:
            existing = await conn.fetchrow(
                "SELECT slug FROM platforms WHERE slug = $1", slug
            )

        content_type = classify_extractor(info["name"])
        website = KNOWN_WEBSITES.get(slug)
        importance = IMPORTANCE_BY_CATEGORY.get(content_type, 0)
        display_name = info["name"].replace("_", " ").title()
        status = info["status"]

        if existing:
            async with get_conn() as conn:
                await conn.execute(
                    """UPDATE platforms SET
                        status = $1, content_type = $2, website = COALESCE(website, $3),
                        yt_dlp_extractor = $4, importance = $5
                       WHERE slug = $6""",
                    status, content_type, website, info["name"], importance, slug,
                )
            updated += 1
        else:
            async with get_conn() as conn:
                await conn.execute(
                    """INSERT INTO platforms
                        (slug, name, status, content_type, website, yt_dlp_extractor, importance)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       ON CONFLICT (slug) DO UPDATE SET
                        status = EXCLUDED.status,
                        content_type = EXCLUDED.content_type,
                        yt_dlp_extractor = EXCLUDED.yt_dlp_extractor,
                        importance = EXCLUDED.importance""",
                    slug, display_name, status, content_type, website, info["name"], importance,
                )
            inserted += 1
        skipped += 1

    print(f"✅ {inserted} insérées, {updated} mises à jour, {skipped - inserted - updated} déjà à jour")
    print(f"   Broken: {sum(1 for e in extractors.values() if e['is_broken'])}")
    print(f"   Content types: {set(classify_extractor(e['name']) for e in extractors.values())}")

    # Stats finales
    async with get_conn() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM platforms")
        print(f"   Total en base : {total}")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(sync_platforms())
