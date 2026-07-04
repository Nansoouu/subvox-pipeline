"""
core/openrouter.py — Client OpenRouter (DeepSeek V3) — Subvox
Extrait depuis conflict-map : uniquement la partie traduction SRT + résumé.
OSINT / géocodage / citations supprimés.
"""

import json
import re
import os
import httpx
from pathlib import Path
from typing import Any

from core.config import settings
from core.logging_setup import get_logger
from core.llm.prompts import (
    SUMMARY_SYSTEM_PROMPT,
    SEGMENTED_SUMMARY_PROMPT,
    ORCHESTRATOR_PROMPT,
    TRANSLATE_SUMMARY_SYSTEM_PROMPT,
)

logger = get_logger(__name__)

# ── Modèles ───────────────────────────────────────────────
PRIMARY_MODEL = "deepseek-chat"
FALLBACK_MODEL = "gpt-4o-mini"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OPENROUTER_TIMEOUT = 90.0
_OPENROUTER_KEY: str | None = None


def _get_openrouter_key() -> str | None:
    """Récupère la clé OpenRouter : env var > settings > None."""
    global _OPENROUTER_KEY
    if _OPENROUTER_KEY:
        return _OPENROUTER_KEY
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        key = getattr(settings, "OPENROUTER_API_KEY", "") or ""
    if not key:
        # Dernier recours : tenter de lire depuis le fichier Hermes auth
        try:
            auth_path = Path.home() / ".hermes" / "auth.json"
            if auth_path.exists():
                import json
                data = json.loads(auth_path.read_text())
                pool = data.get("credential_pool", {}).get("openrouter", [])
                if pool:
                    key = pool[0].get("access_token", "")
        except Exception:
            pass
    if key:
        _OPENROUTER_KEY = key
    return _OPENROUTER_KEY or None

# ── Tarifs ($/M tokens) ────────────────────────
PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {
        "input_per_m": 0.27,
        "output_per_m": 1.10,
    },
    "deepseek/deepseek-chat-v3.1": {
        "input_per_m": 0.89,
        "output_per_m": 1.79,
    },
    "openai/gpt-4o-mini": {
        "input_per_m": 0.15,
        "output_per_m": 0.60,
    },
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calcule le coût estimé d'un appel API en dollars."""
    p = PRICING.get(model, PRICING["deepseek/deepseek-chat-v3.1"])
    cost = (tokens_in * p["input_per_m"] + tokens_out * p["output_per_m"]) / 1_000_000
    return round(cost, 6)


def _extract_json_from_text(text: str) -> dict | None:
    """Extrait un JSON d'un texte markdown/bruite."""
    # Essayer de trouver ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback: parser le texte directement
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


# ── Noms de langues pour le prompt (clés = ISO 639-1) ─────
SUBTITLE_LANG_NAMES: dict[str, str] = {
    "ar": "Arabic (Modern Standard Arabic, clear and natural)",
    "ru": "Russian",
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "zh": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "he": "Hebrew",
    "fa": "Persian",
    "hi": "Hindi",
    "id": "Indonesian",
    "uk": "Ukrainian",
}

# ── Cache simple (en mémoire) ─────────────────────────────
# asyncio.Lock pour thread-safety des accès concurrents
import asyncio as _asyncio

_CACHE: dict[str, Any] = {}
_cache_hits = 0
_cache_misses = 0
_cache_lock = _asyncio.Lock()


async def _from_cache(key: str):
    async with _cache_lock:
        return _CACHE.get(key)


async def _to_cache(key: str, value: Any, ttl: int = 600):
    async with _cache_lock:
        _CACHE[key] = value


# ── Appel générique OpenRouter ──────────────────────────────


async def call_openrouter(
    messages: list[dict],
    model: str = PRIMARY_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    user_id: str = "anonymous",
    cache_key: str = "",
    step_name: str = "",
) -> tuple[str | None, int, int]:
    """
    Appel générique à DeepSeek ou OpenRouter selon le modèle.

    Routage automatique :
      - deepseek-*  → DeepSeek API (texte)
      - google/*    → OpenRouter (vision)
      - groq/*      → Groq API (vision/audio)
      - openai/*    → OpenRouter
      - autre       → DeepSeek par défaut

    Le coût est automatiquement enregistré dans job_metrics si user_id
    contient un job_id (format "job_{uuid}" ou "{uuid}").
    Retourne (contenu | None, tokens_in, tokens_out).
    """
    import time as _time

    # ── Déterminer la route selon le modèle ──
    model_lower = model.lower()

    # Modèles vision → OpenRouter
    vision_prefixes = ("google/", "anthropic/", "openai/", "meta-llama/")
    is_vision_model = model_lower.startswith(vision_prefixes)

    # Modèles texte DeepSeek
    is_deepseek_model = model_lower.startswith("deepseek") or model_lower == PRIMARY_MODEL

    if is_vision_model:
        api_url = OPENROUTER_URL
        api_key = _get_openrouter_key()
        if not api_key:
            logger.warning("Aucune clé OpenRouter configurée pour le modèle vision %s", model)
            return None, 0, 0
    elif is_deepseek_model:
        api_url = DEEPSEEK_URL
        api_key = getattr(settings, "DEEPSEEK_API_KEY", None)
        if not api_key:
            # Fallback: try community pool
            try:
                import httpx as _hx
                _r = _hx.get(f"{settings.ECONOMY_URL}/billing/deepseek-key/pool", timeout=5)
                if _r.status_code == 200:
                    _d = _r.json()
                    if _d.get("key"):
                        api_key = _d["key"]
                        logger.info("Clé DeepSeek du pool communautaire")
            except Exception:
                pass
        if not api_key:
            # Direct DB fallback
            try:
                import asyncio as _aio
                import asyncpg as _apg
                from core.crypto import decrypt_groq_key as _dgk
                async def _fetch_ds():
                    _db = await _apg.connect(settings.DATABASE_URL)
                    try:
                        _row = await _db.fetchrow("SELECT deepseek_key_enc FROM subvox_deepseek_pool WHERE is_active = TRUE LIMIT 1")
                        if _row:
                            _dec = _dgk(_row["deepseek_key_enc"])
                            if _dec:
                                return _dec
                        return None
                    finally:
                        await _db.close()
                _pk = _aio.run(_fetch_ds())
                if _pk:
                    api_key = _pk
                    logger.info("Clé DeepSeek du pool (DB direct)")
            except Exception as _de:
                logger.warning(f"DB DeepSeek pool failed: {_de}")
        if not api_key:
            logger.warning("Aucune clé DEEPSEEK_API_KEY configurée")
            return None, 0, 0
        # Nettoyer le préfixe openrouter si présent
        if model.startswith("deepseek/"):
            model = model.replace("deepseek/", "")
    else:
        # Fallback : DeepSeek
        api_url = DEEPSEEK_URL
        api_key = getattr(settings, "DEEPSEEK_API_KEY", None)
        if not api_key:
            import httpx as _hx2
            try:
                _r2 = _hx2.get(f"{settings.ECONOMY_URL}/billing/deepseek-key/pool", timeout=5)
                if _r2.status_code == 200 and _r2.json().get("key"):
                    api_key = _r2.json()["key"]
            except Exception:
                pass
        if not api_key:
            logger.warning("Aucune clé API configurée pour le modèle %s", model)
            return None, 0, 0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Cache hit
    if cache_key:
        cached = await _from_cache(cache_key)
        if cached is not None:
            global _cache_hits
            _cache_hits += 1
            logger.debug("LLM cache HIT", extra={"cache_key": cache_key[:40]})
            return cached, 0, 0

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "user": user_id,
    }

    try:
        start_time = _time.monotonic()
        async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
        duration_ms = round((_time.monotonic() - start_time) * 1000)
        extra = {
            "model": model,
            "status": resp.status_code,
            "duration_ms": duration_ms,
        }

        if resp.status_code != 200:
            logger.error(
                "OpenRouter HTTP error",
                extra={**extra, "detail": resp.text[:300]},
            )
            return None, 0, 0

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        tokens_in = data.get("usage", {}).get("prompt_tokens", 0)
        tokens_out = data.get("usage", {}).get("completion_tokens", 0)

        cost = _estimate_cost(model, tokens_in, tokens_out)

        logger.info(
            "OpenRouter success",
            extra={
                **extra,
                "step": step_name or "unknown",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_display": f"${cost:.6f}",
                "cost_eur": f"{cost * 0.92:.6f}",
                "user_id": user_id[:8],
            },
        )

        # Auto-record cost from user_id (format: "job_{uuid}" or "{uuid}")
        _job_id = ""
        if user_id and user_id != "anonymous":
            _job_id = user_id.replace("job_", "", 1) if user_id.startswith("job_") else user_id
        if _job_id and tokens_in > 0:
            try:
                from core.pipeline.metrics import get_collector
                get_collector(_job_id).record_llm_call(
                    step_name=step_name or "unknown",
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_eur=cost,
                )
            except Exception:
                pass  # Non bloquant

        # Cache miss → store
        if cache_key:
            await _to_cache(cache_key, content)
            global _cache_misses
            _cache_misses += 1

        return content, tokens_in, tokens_out

    except httpx.TimeoutException:
        logger.error(
            "OpenRouter timeout", extra={"model": model, "timeout": OPENROUTER_TIMEOUT}
        )
        return None, 0, 0
    except Exception as e:
        logger.error("OpenRouter exception", extra={"model": model, "error": str(e)})
        return None, 0, 0


# ── Résumé vidéo (LLM) ────────────────────────────────────


async def generate_summary(
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "",
    video_title: str = "",
    video_description: str = "",
    user_id: str = "",
) -> str:
    """
    Génère une description de la vidéo via DeepSeek V3 à partir :
    - du titre de la vidéo
    - de la description publique
    - des sous-titres (transcript)
    """
    target = target_lang or source_lang
    lang_name = SUBTITLE_LANG_NAMES.get(target, target)

    # Tronquer le transcript
    max_chars = 6000
    truncated = transcript_text[:max_chars]
    if len(transcript_text) > max_chars:
        truncated += "\n\n[... transcription tronquée à 6000 caractères ...]"

    # Construction du user prompt avec contexte vidéo
    user_parts = []
    if video_title:
        user_parts.append(f"Titre : {video_title}")
    if video_description:
        # Limiter la description aussi
        desc = video_description[:2000]
        if len(video_description) > 2000:
            desc += " [...]"
        user_parts.append(f"Description : {desc}")
    user_parts.append(f"Sous-titres (SRT) :\n\n{truncated}")

    system_content = SUMMARY_SYSTEM_PROMPT.format(
        target_lang=lang_name,
    )

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": "\n\n".join(user_parts),
        },
    ]

    content, _, _ = await call_openrouter(
        messages,
        model=PRIMARY_MODEL,
        temperature=0.3,
        max_tokens=1024,
        cache_key=f"summary_{target}_{truncated[:100]}",
        step_name="summary",
        user_id=user_id or "anonymous",
    )
    return (content or "").strip()


async def generate_segmented_summary(
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "",
    video_title: str = "",
    video_description: str = "",
    max_chars: int = 30000,
    user_id: str = "",
) -> dict | None:
    """
    Génère un sommaire structuré (résumé global + segments thématiques)
    via DeepSeek V3 à partir du transcript SRT.

    Retourne un dict avec `global_summary` et `segments` (liste), ou None si échec.
    """
    target = target_lang or source_lang
    lang_name = SUBTITLE_LANG_NAMES.get(target, target)

    max_label = max_chars
    # Tronquer le transcript (large pour les vidéos longues)
    truncated = transcript_text[:max_chars]
    if len(transcript_text) > max_chars:
        truncated += f"\n\n[... transcription tronquée à {max_label} caractères ...]"

    # Construction du user prompt
    user_parts = []
    if video_title:
        user_parts.append(f"Titre : {video_title}")
    if video_description:
        desc = video_description[:2000]
        if len(video_description) > 2000:
            desc += " [...]"
        user_parts.append(f"Description : {desc}")
    user_parts.append(f"Sous-titres (SRT) :\n\n{truncated}")

    system_content = SEGMENTED_SUMMARY_PROMPT.format(
        target_lang=lang_name,
    )

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": "\n\n".join(user_parts),
        },
    ]

    content, _, _ = await call_openrouter(
        messages,
        model=PRIMARY_MODEL,
        temperature=0.3,
        max_tokens=4096,
        cache_key=f"segmented_summary_{target}_{max_chars}_{truncated[:100]}",
        step_name="summary",
        user_id=user_id or "anonymous",
    )

    if not content:
        logger.warning("generate_segmented_summary: réponse LLM vide")
        return None

    return _parse_json_response(content)


def _parse_json_response(content: str) -> dict | None:
    """
    Parse une réponse JSON depuis le LLM, avec gestion des blocs markdown,
    caractères d'échappement et retours à la ligne dans les chaînes.
    Multiple stratégies de fallback pour maximiser le taux de succès.
    """
    import re as _re

    cleaned = content.strip()

    # 1. Extraire le bloc ```json ... ``` ou ``` ... ```
    match = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, _re.DOTALL)
    if match:
        cleaned = match.group(1).strip()

    # 2. Nettoyer les backslashs problématiques (\\n, \\", etc.)
    # que le LLM insère parfois dans les chaînes JSON
    cleaned = _re.sub(r"(?<!\\)\\(?![\"\\\/bfnrtu])", "", cleaned)

    # 3. Tentative de parsing avec plusieurs variantes
    data = None
    candidates = [
        cleaned,
        # Remplacer les virgules avant } (JSON strict ne les accepte pas)
        _re.sub(r",\s*}", "}", cleaned),
        _re.sub(r",\s*\]", "]", cleaned),
        # Fallback sur le contenu original
        content.strip(),
    ]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                break
        except (json.JSONDecodeError, TypeError):
            continue

    # 4. Fallback extract_json_from_text
    if data is None:
        logger.warning(
            "generate_segmented_summary: JSON direct échoué, "
            "tentative d'extraction regex"
        )
        logger.debug(
            "generate_segmented_summary: réponse brute (500 premiers chars)",
            extra={"raw_response": content[:500]},
        )
        data = _extract_json_from_text(content)

    # 5. Fallback: chercher le premier { et dernier } dans le texte
    if data is None:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw_json = content[start:end+1]
            for strategy in [
                raw_json,
                _re.sub(r",\s*}", "}", raw_json),
                _re.sub(r",\s*\]", "]", raw_json),
            ]:
                try:
                    data = json.loads(strategy)
                    if isinstance(data, dict):
                        logger.info(
                            "generate_segmented_summary: succès avec extraction { }"
                        )
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

    if data is None:
        logger.error(
            "generate_segmented_summary: tous les fallbacks ont échoué",
            extra={"raw_preview": content[:500]},
        )
        return None

    # 5. Validation basique
    if not isinstance(data, dict):
        logger.warning("generate_segmented_summary: la réponse n'est pas un dict")
        return None
    if "global_summary" not in data:
        logger.warning("generate_segmented_summary: clé global_summary manquante")
        data["global_summary"] = ""
    if "segments" not in data or not isinstance(data.get("segments"), list):
        logger.warning(
            "generate_segmented_summary: clé segments manquante ou pas une liste"
        )
        data["segments"] = []

    return data


# ── Résumé adaptatif 3 tiers ──────────────────────────────

# Seuils en nombre de caractères du transcript
TIER_SHORT_MAX = 15000  # Courte : < 15K chars (~15 min)
TIER_MEDIUM_MAX = 50000  # Moyenne : 15K-50K chars (~15-45 min)
# Longue : > 50K chars


async def generate_adaptive_summary(
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "",
    video_title: str = "",
    video_description: str = "",
    user_id: str = "",
) -> dict:
    """
    Génère un résumé adaptatif selon la longueur du transcript :
    - TIER 1 (court)  : generate_segmented_summary() direct (max 30K chars)
    - TIER 2 (moyen)  : generate_segmented_summary() direct (max 60K chars)
    - TIER 3 (long)   : split → parallélisation → orchestrateur

    Retourne dict avec 'global_summary', 'segments', 'tier' (1|2|3).
    """
    target = target_lang or source_lang
    total_chars = len(transcript_text)

    logger.info(
        "generate_adaptive_summary",
        extra={
            "total_chars": total_chars,
            "source_lang": source_lang,
            "target_lang": target,
        },
    )

    if total_chars <= TIER_SHORT_MAX:
        logger.info(
            "Tier 1 (court) — appel direct",
            extra={"total_chars": total_chars, "max": TIER_SHORT_MAX},
        )
        data = await generate_segmented_summary(
            transcript_text=transcript_text,
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=video_title,
            video_description=video_description,
            max_chars=30000,
            user_id=user_id,
        )
        if data is None:
            return {"global_summary": "", "segments": [], "tier": 1}
        data["tier"] = 1
        return data

    if total_chars <= TIER_MEDIUM_MAX:
        logger.info(
            "Tier 2 (moyen) — appel direct avec max_chars=60000",
            extra={"total_chars": total_chars, "max": TIER_MEDIUM_MAX},
        )
        data = await generate_segmented_summary(
            transcript_text=transcript_text,
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=video_title,
            video_description=video_description,
            max_chars=60000,
            user_id=user_id,
        )
        if data is None:
            return {"global_summary": "", "segments": [], "tier": 2}
        data["tier"] = 2
        return data

    # Tier 3 (long) : split + parallélisation + orchestrateur
    logger.info(
        "Tier 3 (long) — mode orchestrateur",
        extra={"total_chars": total_chars},
    )
    data = await _generate_long_video_summary(
        transcript_text=transcript_text,
        source_lang=source_lang,
        target_lang=target_lang,
        video_title=video_title,
        video_description=video_description,
        user_id=user_id,
    )
    if data is None:
        return {"global_summary": "", "segments": [], "tier": 3}
    data["tier"] = 3
    return data


def _split_transcript_into_chunks(
    transcript_text: str,
    chunk_chars: int = 15000,
) -> list[tuple[int, int, str]]:
    """
    Découpe le transcript SRT en chunks de ~chunk_chars caractères.
    Les coupes se font entre les blocs SRT pour ne pas couper au milieu d'un bloc.

    Retourne une liste de (index, total_chunks, text_chunk).
    """
    if not transcript_text.strip():
        return []

    # Découper en blocs SRT
    blocks = transcript_text.strip().split("\n\n")
    chunks: list[str] = []
    current = []

    for block in blocks:
        current.append(block)
        if len("\n\n".join(current)) >= chunk_chars:
            chunks.append("\n\n".join(current))
            current = []

    if current:
        chunks.append("\n\n".join(current))

    if not chunks:
        chunks.append(transcript_text)

    result = []
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        result.append((i, n, chunk))

    return result


async def _generate_long_video_summary(
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "",
    video_title: str = "",
    video_description: str = "",
    user_id: str = "",
) -> dict | None:
    """
    Tier 3 : split le transcript en chunks parallélisés, puis orchestre la fusion.

    Étapes :
    1. Split en 3-5 chunks de ~15K chars
    2. Appels LLM parallèles (asyncio.gather) — chaque chunk → segments
    3. Appel orchestrateur pour sélectionner les meilleurs segments + résumé global
    """
    import asyncio
    import time as _time

    target = target_lang or source_lang
    lang_name = SUBTITLE_LANG_NAMES.get(target, target)

    # 1. Split
    chunk_chars = 15000
    chunks = _split_transcript_into_chunks(transcript_text, chunk_chars)
    n_chunks = len(chunks)

    print(
        f"  ⏳ Tier 3 — Split du transcript en {n_chunks} chunks (~{chunk_chars} chars/chunk)"
    )

    logger.info(
        "Long video: split en chunks",
        extra={"n_chunks": n_chunks, "chunk_chars": chunk_chars},
    )

    if n_chunks == 0:
        return None

    # 2. Appels parallèles
    print(f"  ⏳ Lancement de {n_chunks} appels LLM en parallèle...")

    async def _process_chunk(index: int, total: int, chunk_text: str) -> list[dict]:
        """Analyse un chunk et retourne ses segments."""
        chunk_label = f"Partie {index + 1}/{total}"
        t0 = _time.monotonic()

        # Marquer les timestamps relatifs avec le label du chunk
        chunk_title = f"{video_title} — {chunk_label}" if video_title else chunk_label

        chunk_data = await generate_segmented_summary(
            transcript_text=chunk_text,
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=chunk_title,
            video_description=video_description,
            max_chars=chunk_chars + 2000,  # un peu de marge
            user_id=user_id,
        )

        duration = _time.monotonic() - t0
        if chunk_data and chunk_data.get("segments"):
            segments = chunk_data["segments"]
            n = len(segments)
            print(
                f"     ✅ Chunk {index + 1}/{total} analysé — {n} segments trouvés ({duration:.1f}s)"
            )
            logger.info(
                "Chunk analysé",
                extra={
                    "chunk": index + 1,
                    "total": total,
                    "segments": n,
                    "duration_s": round(duration, 1),
                },
            )
            return segments
        print(
            f"     ⚠️ Chunk {index + 1}/{total} — 0 segments trouvés ({duration:.1f}s)"
        )
        return []

    all_candidate_segments: list[dict] = []
    chunk_tasks = [
        _process_chunk(i, n_chunks, chunk_text) for i, n_chunks, chunk_text in chunks
    ]

    results = await asyncio.gather(*chunk_tasks)
    for seg_list in results:
        all_candidate_segments.extend(seg_list)

    logger.info(
        "Tous les chunks analysés",
        extra={"total_candidates": len(all_candidate_segments)},
    )

    if not all_candidate_segments:
        logger.warning("Long video: aucun segment candidat trouvé")
        return None

    # 3. Orchestrateur : sélectionner les meilleurs segments
    # On cible 8-12 segments pour les vidéos longues
    n_candidates = len(all_candidate_segments)
    target_count = min(max(8, n_candidates // 2), 12)

    system_content = ORCHESTRATOR_PROMPT.format(
        target_lang=lang_name,
        candidate_count=n_candidates,
        target_count=target_count,
        min_segments=6,
        max_segments=12,
    )

    # Sérialiser les segments candidats pour le prompt
    candidates_json = json.dumps(
        [
            {
                "start_ts": s.get("start_ts", ""),
                "end_ts": s.get("end_ts", ""),
                "title": s.get("title", ""),
                "summary": s.get("summary", ""),
                "highlight": s.get("highlight", ""),
                "reason": s.get("reason", ""),
            }
            for s in all_candidate_segments
        ],
        ensure_ascii=False,
        indent=2,
    )

    user_parts = []
    if video_title:
        user_parts.append(f"Titre : {video_title}")
    if video_description:
        desc = video_description[:2000]
        if len(video_description) > 2000:
            desc += " [...]"
        user_parts.append(f"Description : {desc}")
    user_parts.append(
        f"Segments candidats (extraits des différentes parties de la vidéo) :\n\n{candidates_json}"
    )

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": "\n\n".join(user_parts),
        },
    ]

    print(
        f"  ⏳ Orchestrateur — sélection des {target_count} meilleurs segments parmi {n_candidates} candidats..."
    )
    t_orch = _time.monotonic()

    content, tokens_in, tokens_out = await call_openrouter(
        messages,
        model=PRIMARY_MODEL,
        temperature=0.3,
        max_tokens=4096,
        cache_key=f"orchestrator_{target}_{n_candidates}_{(video_title or 'untitled')[:50]}",
    )

    if not content:
        print(
            f"     ⚠️ Orchestrateur: réponse vide, fallback ({_time.monotonic() - t_orch:.1f}s)"
        )
        logger.warning(
            "Orchestrator: réponse LLM vide, fallback sur tous les candidats"
        )
        # Fallback : retourner tous les segments candidats triés
        return {
            "global_summary": f"Vidéo analysée en {n_chunks} parties, {n_candidates} segments identifiés.",
            "segments": sorted(
                all_candidate_segments,
                key=lambda s: s.get("start_ts", ""),
            ),
        }

    # Parser le résultat de l'orchestrateur
    orchestrated = _parse_json_response(content)

    if orchestrated is None or not orchestrated.get("segments"):
        logger.warning(
            "Orchestrator: JSON invalide ou vide, fallback sur tous les candidats"
        )
        print(
            f"     ⚠️ Orchestrateur: JSON invalide, fallback ({_time.monotonic() - t_orch:.1f}s)"
        )
        return {
            "global_summary": f"Vidéo analysée en {n_chunks} parties, {n_candidates} segments identifiés.",
            "segments": sorted(
                all_candidate_segments,
                key=lambda s: s.get("start_ts", ""),
            ),
        }

    n_selected = len(orchestrated.get("segments", []))
    orch_duration = _time.monotonic() - t_orch

    logger.info(
        "Orchestrateur terminé",
        extra={
            "n_candidates": n_candidates,
            "n_selected": n_selected,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_s": round(orch_duration, 1),
        },
    )

    print(
        f"     ✅ Orchestrateur — {n_candidates} → {n_selected} segments sélectionnés ({orch_duration:.1f}s)"
    )
    print(
        f"  ✅ Tier 3 terminé — {n_selected} segments | durée totale : {orch_duration:.1f}s"
    )

    return orchestrated


# ── Traduction SRT ────────────────────────────────────────


def _extract_timestamp(timecode_line: str) -> str:
    """Extrait la partie timestamp 'start --> end' d'une ligne SRT brute."""
    return timecode_line.strip()


def _restore_original_timestamps(
    translated: str,
    original_timestamps: list[str],
) -> str:
    """
    Remplace les timestamps dans le SRT traduit par les originaux.

    Le LLM modifie parfois les timestamps malgré les instructions.
    Cette fonction restaure les timestamps originaux bloc par bloc.

    Args:
        translated: SRT traduit (avec timestamps potentiellement corrompus)
        original_timestamps: Liste des timecodes originaux dans l'ordre

    Returns:
        SRT avec timestamps restaurés, ou translated inchangé si échec
    """
    lines = translated.strip().splitlines()
    result: list[str] = []
    ts_idx = 0

    for line in lines:
        stripped = line.strip()
        # Si la ligne ressemble à un timecode, on la remplace par l'original
        if " --> " in stripped and ts_idx < len(original_timestamps):
            result.append(original_timestamps[ts_idx])
            ts_idx += 1
        else:
            result.append(line)

    return "\n".join(result)


async def translate_srt(
    srt_content: str,
    source_lang: str,
    target_lang: str,
    user_id: str = "",
) -> str | None:
    """
    Traduit un contenu SRT via DeepSeek V3.
    Gère le chunking et la fusion avec détection d'échec.
    Restaure les timestamps originaux après traduction pour éviter la corruption.
    """
    if target_lang == source_lang:
        return srt_content

    src_name = SUBTITLE_LANG_NAMES.get(source_lang, source_lang)
    tgt_name = SUBTITLE_LANG_NAMES.get(target_lang, target_lang)

    cache_key = f"srt_{source_lang}_{target_lang}_{srt_content[:80]}"
    cached = await _from_cache(cache_key)
    if cached is not None:
        logger.info(
            f"OpenRouter SRT cache HIT {source_lang}→{target_lang}",
            extra={"src": source_lang, "tgt": target_lang},
        )
        return cached

    # Extraire les timestamps originaux AVANT traduction
    original_timestamps: list[str] = []
    for block in srt_content.strip().split("\n\n"):
        for line in block.splitlines():
            if " --> " in line.strip():
                original_timestamps.append(line.strip())
                break

    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional subtitle translator. "
                "You will receive an SRT subtitle file and must translate it "
                f"from {src_name} to {tgt_name}.\n\n"
                "IMPORTANT RULES:\n"
                "1. Keep the SRT structure EXACTLY as is (timestamps, numbering, spacing).\n"
                "2. Translate ONLY the text between the timestamp lines.\n"
                "3. Never translate or modify timestamps (e.g., '00:00:01,000 --> 00:00:03,500').\n"
                "4. Never add new lines, extra spacing, or commentary.\n"
                "5. Keep the same number of subtitle blocks.\n"
                "6. If a line has no text or is empty, keep it as is.\n"
                "7. Maintain natural reading flow in the target language.\n"
                f"8. Output ONLY the translated SRT content, no explanations."
            ),
        },
        {
            "role": "user",
            "content": f"Translate this SRT from {src_name} to {tgt_name}:\n\n{srt_content}",
        },
    ]

    content, tokens_in, tokens_out = await call_openrouter(
        messages,
        model=PRIMARY_MODEL,
        temperature=0.3,
        max_tokens=8192,
        cache_key=cache_key,
        step_name="translating",
        user_id=user_id or "anonymous",
    )
    if not content:
        logger.error(
            f"OpenRouter SRT translation failed {source_lang}→{target_lang}",
            extra={"src": source_lang, "tgt": target_lang},
        )
        return None

    # Vérifier que le résultat ressemble à un SRT valide
    if " --> " not in content and "\n00:" not in content:
        logger.warning(
            f"OpenRouter SRT {source_lang}→{target_lang} : résultat ne ressemble pas à un SRT, "
            f"utilisation du fallback",
            extra={"src": source_lang, "tgt": target_lang},
        )
        return None

    # Restaurer les timestamps originaux (le LLM peut les modifier malgré les instructions)
    content = _restore_original_timestamps(content, original_timestamps)

    # Validation : compter les blocs
    original_block_count = len(original_timestamps)
    translated_block_count = len(
        [b for b in content.strip().split("\n\n") if " --> " in b]
    )

    # Seuil plus strict : on tolère max 5% de perte (contre 20% avant)
    ratio = translated_block_count / max(original_block_count, 1)
    if ratio < 0.95:
        logger.warning(
            f"OpenRouter SRT {source_lang}→{target_lang} : "
            f"trop de blocs après restauration ({translated_block_count}/{original_block_count}), fallback",
            extra={"src": source_lang, "tgt": target_lang},
        )
        return srt_content

    cost = _estimate_cost(PRIMARY_MODEL, tokens_in, tokens_out)
    logger.info(
        f"OpenRouter SRT translation OK: {source_lang}→{target_lang} — "
        f"{tokens_in}+{tokens_out} tokens → ${cost:.6f} ({len(content)} chars, {translated_block_count} blocs)",
        extra={
            "src": source_lang,
            "tgt": target_lang,
            "blocks": translated_block_count,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_display": f"${cost:.6f}",
        },
    )
    await _to_cache(cache_key, content)
    return content


# ── Traduction de résumé (optimisation multi-langues) ─────


async def translate_summary(
    text: str,
    source_lang: str = "en",
    target_lang: str = "fr",
) -> str | None:
    """
    Traduit un court texte (résumé, titre) d'une langue source vers une langue cible.
    Utilise un appel LLM léger (peu de tokens) pour préserver le ton et la fluidité.
    """
    if target_lang == source_lang or not text:
        return text

    src_name = SUBTITLE_LANG_NAMES.get(source_lang, source_lang)
    tgt_name = SUBTITLE_LANG_NAMES.get(target_lang, target_lang)

    system_content = TRANSLATE_SUMMARY_SYSTEM_PROMPT.format(
        source_lang=src_name,
        target_lang=tgt_name,
    )

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": text,
        },
    ]

    cache_key = f"trans_summary_{source_lang}_{target_lang}_{text[:80]}"
    content, _, _ = await call_openrouter(
        messages,
        model=PRIMARY_MODEL,
        temperature=0.3,
        max_tokens=512,
        cache_key=cache_key,
    )

    if not content:
        logger.warning(
            "translate_summary: réponse LLM vide, garde texte original",
            extra={"src": source_lang, "tgt": target_lang, "text_len": len(text)},
        )
        return text

    translated = content.strip()
    logger.info(
        "translate_summary OK",
        extra={
            "src": source_lang,
            "tgt": target_lang,
            "chars_before": len(text),
            "chars_after": len(translated),
        },
    )
    return translated


# ── Stats cache ───────────────────────────────────────────


def get_cache_stats() -> dict:
    return {"hits": _cache_hits, "misses": _cache_misses, "size": len(_CACHE)}
