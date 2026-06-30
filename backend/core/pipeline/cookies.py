"""
pipeline/cookies.py — Validation des cookies X/Twitter — Subvox
"""

from core.logging_setup import get_logger

logger = get_logger(__name__)


def _is_valid_cookies_file(cookies_path: str) -> bool:
    """
    Valide le fichier cookies.txt.
    Retourne True si le fichier existe, n'est pas vide,
    a le format Netscape et contient au moins auth_token ou ct0.
    """
    import os
    import time

    if not os.path.exists(cookies_path):
        return False

    size = os.path.getsize(cookies_path)
    if size == 0:
        logger.error("Fichier cookies vide", extra={"size": size, "path": cookies_path})
        return False

    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            logger.error("Fichier cookies sans lignes", extra={"path": cookies_path})
            return False

        # Verifier le format Netscape
        first_line = lines[0].strip()
        if not first_line.startswith("# Netscape HTTP Cookie File"):
            logger.error(
                "Format Netscape non detecte",
                extra={"path": cookies_path, "first_line": first_line[:50]},
            )
            return False

        # Verifier la presence de cookies essentiels pour X/Twitter
        has_auth_token = any("auth_token" in line for line in lines)
        has_ct0 = any("ct0" in line for line in lines)

        # Verifier l'expiration des cookies
        current_time = int(time.time())
        expired_cookies = 0
        for line in lines:
            if line.strip().startswith("#") or "\t" not in line:
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 5:
                try:
                    expiry = int(parts[4])
                    if expiry != 0 and expiry < current_time:
                        expired_cookies += 1
                except ValueError:
                    pass

        if not has_auth_token and not has_ct0:
            logger.warning(
                "Aucun cookie X/Twitter (auth_token/ct0) trouve",
                extra={"path": cookies_path},
            )

        if expired_cookies > 0:
            logger.warning(
                "Cookies expires detectes",
                extra={"count": expired_cookies, "path": cookies_path},
            )

        logger.info(
            "Cookies valides",
            extra={
                "path": cookies_path,
                "size": size,
                "lines": len(lines),
                "has_auth_token": has_auth_token,
                "has_ct0": has_ct0,
                "expired": expired_cookies,
            },
        )
        return True

    except Exception as e:
        logger.error(
            "Erreur validation cookies",
            extra={"path": cookies_path, "error": str(e)},
        )
        return False
