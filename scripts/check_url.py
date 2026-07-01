#!/usr/bin/env python3
"""
URL Validator — Vérifie si une URL vidéo peut être traitée par le pipeline.

Usage:
    python3 scripts/check_url.py https://x.com/user/status/123/video/1
    python3 scripts/check_url.py --all  (teste les URLs en DB)
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys

# Config
TIMEOUT = 15  # secondes
YTDLP = "yt-dlp"


def check_ytdlp(url: str, cookies: str | None = None) -> dict:
    """Teste yt-dlp sur une URL. Retourne infos ou erreur."""
    cmd = [
        YTDLP, "--print", "%(title)s|%(extractor)s|%(duration)s|%(resolution)s",
        "--no-download", "--no-warnings",
        url,
    ]
    if cookies:
        cmd.extend(["--cookies", cookies])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|")
            return {
                "status": "ok",
                "title": parts[0] if len(parts) > 0 else "",
                "source": parts[1] if len(parts) > 1 else "unknown",
                "duration_s": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                "resolution": parts[3] if len(parts) > 3 else "",
            }
        # Analyser l'erreur
        stderr = result.stderr.lower()
        if "http error 404" in stderr:
            return {"status": "not_found", "error": "404 — Vidéo introuvable"}
        if "http error 403" in stderr or "403" in stderr:
            return {"status": "needs_cookies", "error": "403 — Cookies requis"}
        if "private video" in stderr or "private" in stderr:
            return {"status": "private", "error": "Vidéo privée"}
        if "age" in stderr or "age-gate" in stderr:
            return {"status": "age_restricted", "error": "Vidéo restreinte (âge)"}
        if "unsupported url" in stderr:
            return {"status": "unsupported", "error": "Site non supporté"}
        return {
            "status": "error",
            "error": stderr[:200] if stderr else "Erreur inconnue",
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Timeout ({TIMEOUT}s)"}
    except FileNotFoundError:
        return {"status": "error", "error": "yt-dlp non installé"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def test_url(url: str, cookies: str | None = None) -> dict:
    """Test complet d'une URL."""
    result = check_ytdlp(url, cookies)
    result["url"] = url
    result["cookies_used"] = bool(cookies)

    # Suggestions
    suggestions = {
        "ok": "✅ Prêt à traduire",
        "not_found": "❌ Vérifie le lien",
        "needs_cookies": "🍪 Ajoute les cookies (--cookies cookies.txt)",
        "private": "🔒 Passe la vidéo en public",
        "age_restricted": "🔞 Connecte-toi avec un compte",
        "unsupported": "⚠️ Site pas encore supporté",
        "timeout": "⏱️ Site trop lent ou bloqué",
        "error": f"⚠️ {result.get('error', 'Erreur')}",
    }
    result["suggestion"] = suggestions.get(result["status"], "⚠️ Voir erreur")
    return result


def print_result(result: dict):
    """Affiche le résultat proprement."""
    status = result["status"]
    emoji = {
        "ok": "✅", "not_found": "❌", "needs_cookies": "🍪",
        "private": "🔒", "age_restricted": "🔞", "unsupported": "⚠️",
        "timeout": "⏱️", "error": "❌",
    }.get(status, "❓")

    print(f"\n{emoji} {result['url']}")
    print(f"   Statut : {status}")
    print(f"   Suggestion : {result['suggestion']}")

    if status == "ok":
        print(f"   Source  : {result.get('source', '?')}")
        print(f"   Titre   : {result.get('title', '?')[:60]}")
        dur = result.get("duration_s")
        if dur:
            print(f"   Durée   : {dur // 60}:{dur % 60:02d} min")

    if status == "needs_cookies" and not result.get("cookies_used"):
        print("   → Nouveau test AVEC cookies...")
        with_cookies = test_url(result["url"], "cookies.txt")
        print_result(with_cookies)


async def test_db_urls():
    """Teste toutes les URLs uniques de la DB."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    import core.db as db

    await db.init_pool()
    async with db.get_conn() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT source_url FROM jobs WHERE source_url IS NOT NULL"
        )
        urls = [r["source_url"] for r in rows]

    print(f"\n📋 {len(urls)} URLs dans la DB")
    for url in urls:
        result = test_url(url)
        print_result(result)

    await db.close_pool()


def main():
    parser = argparse.ArgumentParser(description="Teste si une URL vidéo est valide")
    parser.add_argument("url", nargs="?", help="URL à tester")
    parser.add_argument("--all", action="store_true", help="Tester toutes les URLs de la DB")
    parser.add_argument("--cookies", help="Fichier cookies.txt")
    args = parser.parse_args()

    if args.all:
        asyncio.run(test_db_urls())
    elif args.url:
        result = test_url(args.url, args.cookies)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
