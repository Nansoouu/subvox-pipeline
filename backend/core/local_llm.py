"""
local_llm.py — Appels LLM locaux via Ollama.

Utilise qwen2.5:1.5b pour la génération de résumés et titres.
Gratuit, privé, fonctionne hors-ligne.
"""

import json
import httpx
from core.logging_setup import get_logger

logger = get_logger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:1.5b"
TIMEOUT = 60


async def generate_summary_local(
    transcript: str,
    source_lang: str = "en",
    target_lang: str = "",
    video_title: str = "",
) -> dict | None:
    """
    Génère un titre + résumé depuis le transcript via Qwen local.
    Retourne {"title": ..., "global_summary": ..., "category": ...}.
    """
    lang_hint = f" in {source_lang}" if source_lang else ""
    prompt = f"""Extract a short title (max 6 words), a single-word category, and a 2-sentence summary from this video transcript{lang_hint}.

Return ONLY valid JSON, no markdown, no extra text:
{{"title": "...", "category": "...", "global_summary": "..."}}

Transcript:
{transcript[:8000]}"""

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "max_tokens": 500},
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Ollama error: HTTP {resp.status_code}")
                return None

            data = resp.json()
            raw = data.get("response", "").strip()

            # Extract JSON from response (handle markdown-wrapped JSON)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            result = json.loads(raw)
            logger.info(
                f"Qwen summary: title={result.get('title','')[:40]} "
                f"summary={len(result.get('global_summary',''))} chars"
            )
            return result

    except httpx.TimeoutException:
        logger.warning("Ollama timeout (60s)")
    except json.JSONDecodeError as e:
        logger.warning(f"Ollama JSON parse error: {e}")
    except Exception as e:
        logger.warning(f"Ollama error: {e}")

    return None
