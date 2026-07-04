"""
core/crypto.py — Chiffrement/déchiffrement des clés Groq
Utilisé par auth.py (API), pipeline_task.py (worker) et credentials.py
"""

from core.config import settings


def encrypt_groq_key(key: str) -> str:
    """Chiffrement AES-256-GCM. Retourne hex(nonce + ciphertext + tag).
    Fallback base64 en dev (pas de GROQ_ENCRYPTION_KEY)."""
    if not settings.GROQ_ENCRYPTION_KEY:
        import base64
        return base64.b64encode(key.encode()).decode()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os

    aes_key = settings.GROQ_ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ct = aesgcm.encrypt(nonce, key.encode(), None)
    return (nonce + ct).hex()


def decrypt_groq_key(encrypted: str) -> str:
    """Déchiffrement AES-256-GCM. Fallback plaintext en dev."""
    if not settings.GROQ_ENCRYPTION_KEY:
        import base64
        try:
            return base64.b64decode(encrypted).decode()
        except Exception:
            return encrypted  # Already plaintext in dev
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = bytes.fromhex(encrypted)
    nonce, ct = raw[:12], raw[12:]
    aes_key = settings.GROQ_ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ct, None).decode()
