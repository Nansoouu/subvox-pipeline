"""
core/ollama.py — Ollama client for local LLM inference — Subvox

Uses Ollama's /api/chat endpoint (OpenAI-compatible) for:
- SRT translation (primary use case)
- Optional: summary generation, text analysis

Fallback: if Ollama is unreachable, falls back to OpenRouter/DeepSeek.
"""

from __future__ import annotations

import httpx
from typing import Any

from core.config import settings
from core.logging_setup import get_logger

logger = get_logger(__name__)

# ── Config ─────────────────────────────────────────────────
OLLAMA_URL = getattr(settings, "OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = getattr(settings, "OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = getattr(settings, "OLLAMA_TIMEOUT", 300.0)  # 5 min for long translations
OLLAMA_CHAT_URL = f"{OLLAMA_URL}/api/chat"


async def call_ollama(
    messages: list[dict[str, str]],
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    **_kwargs: Any,
) -> tuple[str | None, int, int]:
    """
    Appel generique a l'API Ollama (mode chat, OpenAI-compatible).

    Args:
        messages: Liste de dicts {"role": "system"|"user"|"assistant", "content": str}
        model: Modele Ollama (defaut: OLLAMA_MODEL)
        temperature: 0.0-1.0
        max_tokens: Max tokens en sortie

    Returns:
        (content | None, tokens_in, tokens_out)
    """
    model = model or OLLAMA_MODEL

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                OLLAMA_CHAT_URL,
                json=payload,
            )

        if resp.status_code != 200:
            logger.error(
                f"Ollama HTTP {resp.status_code}",
                extra={"detail": resp.text[:300]},
            )
            return None, 0, 0

        data = resp.json()
        content = (data.get("message") or {}).get("content", "")

        # Ollama ne retourne pas toujours token counts
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        logger.info(
            f"Ollama OK: {tokens_in} in / {tokens_out} out",
            extra={"model": model},
        )

        return content, tokens_in, tokens_out

    except httpx.TimeoutException:
        logger.error(f"Ollama timeout ({OLLAMA_TIMEOUT}s)")
        return None, 0, 0
    except httpx.ConnectError:
        logger.warning("Ollama unreachable — is 'ollama serve' running?")
        return None, 0, 0
    except Exception as e:
        logger.error(f"Ollama exception: {str(e)[:200]}")
        return None, 0, 0


async def translate_srt_via_ollama(
    srt_text: str,
    source_lang: str = "en",
    target_lang: str = "fr",
    model: str = "",
) -> str | None:
    """
    Traduit un bloc SRT via Ollama (Qwen2.5).

    Utilise un prompt system simple qui preserve le format SRT.
    """
    from core.openrouter import SUBTITLE_LANG_NAMES

    source_name = SUBTITLE_LANG_NAMES.get(source_lang, source_lang)
    target_name = SUBTITLE_LANG_NAMES.get(target_lang, target_lang)

    system_prompt = (
        f"You are a professional subtitle translator. "
        f"Translate the following SRT subtitles from {source_name} to {target_name}. "
        f"Rules:\n"
        f"1. Preserve ALL SRT timing and numbering EXACTLY as-is\n"
        f"2. Translate only the text, keep the numbers and timestamps unchanged\n"
        f"3. Keep the same number of lines\n"
        f"4. Use natural, fluent {target_name}\n"
        f"5. Output ONLY the translated SRT, no explanations"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Translate this SRT:\n\n{srt_text}"},
    ]

    content, tokens_in, tokens_out = await call_ollama(
        messages,
        model=model or OLLAMA_MODEL,
        temperature=0.1,  # Low temp for translation accuracy
        max_tokens=max(len(srt_text) * 3, 4096),
    )

    if content and ("-->" in content or "\n00:" in content):
        logger.info(
            f"Ollama translation OK ({len(srt_text)}→{len(content)} chars)",
            extra={"tokens_in": tokens_in, "tokens_out": tokens_out},
        )
        return content.strip()

    if content:
        # Fallback: even if format looks wrong, return it
        logger.warning(
            "Ollama response doesn't look like SRT — returning anyway"
        )
        return content.strip()

    return None


async def is_ollama_available() -> bool:
    """Verifie si Ollama est en ligne et le modele est charge."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            if OLLAMA_MODEL in models or any(m.startswith(OLLAMA_MODEL.split(":")[0]) for m in models):
                return True
            logger.warning(f"Ollama model {OLLAMA_MODEL} not found in {models[:5]}")
            return False
    except Exception:
        pass
    return False
