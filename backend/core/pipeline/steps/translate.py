"""
Étape 5 : Traduction SRT avec chunking et parallélisation.
"""

from __future__ import annotations

import asyncio
import os

from core.logging_setup import get_logger
from core.pipeline.duration_tiers import DurationTier
from core.pipeline.srt import _parse_srt
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_translate(
    job_id: str,
    clean_srt: str = "",
    source_lang: str = "en",
    target_lang: str = "fr",
    duration_tier: DurationTier | None = None,
) -> StepResult:
    """
    Traduit le SRT source vers la langue cible via OpenRouter.
    Gère le chunking pour les gros fichiers.
    """
    from core.openrouter import translate_srt
    from core.srt_chunking import should_chunk_srt, chunk_srt, merge_srt_chunks
    from core.config import settings

    log_extra = {"job_id": job_id}
    translated_srt_content = None

    if not clean_srt:
        tmp = _get_tmp(job_id)
        srt_path = tmp / "transcript.srt"
        if srt_path.exists():
            clean_srt = srt_path.read_text(encoding="utf-8")

    if not clean_srt:
        logger.warning(
            "SRT vide apres filtrage — impossible de traduire, pipeline abandonne",
            extra=log_extra,
        )
        return StepResult(
            success=False,
            error="SRT vide apres filtrage — aucun contenu a traduire",
        )

    if target_lang != "none" and target_lang != source_lang and clean_srt:
        try:
            srt_char_count = len(clean_srt)
            blocks = _parse_srt(clean_srt)
            srt_block_count = len(blocks)
            use_chunking = should_chunk_srt(srt_char_count, srt_block_count)
            logger.info(
                f"Traduction {source_lang}->{target_lang}",
                extra={"use_chunking": use_chunking, **log_extra},
            )

            if use_chunking:
                chunks = chunk_srt(
                    clean_srt,
                    max_chars=duration_tier.max_chars_per_chunk if duration_tier else 8000,
                    max_blocks=duration_tier.max_blocks_per_chunk if duration_tier else 60,
                )
                _chunks_total = len(chunks)
                _concurrency = int(os.environ.get("TRANSLATION_CONCURRENCY", "10"))
                logger.info(
                    f"Traduction {source_lang}→{target_lang} : "
                    f"{srt_char_count} chars, {srt_block_count} blocs → {_chunks_total} chunks "
                    f"(concurrency={_concurrency})",
                    extra={
                        **log_extra,
                        "chunks": _chunks_total,
                        "concurrency": _concurrency,
                    },
                )

                # Semaphore pour limiter la concurrence
                _semaphore = asyncio.Semaphore(_concurrency)

                # Télémetry : current progress best-effort (1ère mise à jour)
                try:
                    from core.pipeline.telemetry import set_step_progress as _set_sp

                    await _set_sp(
                        job_id,
                        {
                            "step_name": "translating",
                            "current": 0,
                            "total": _chunks_total,
                            "label": f"0/{_chunks_total} chunks",
                        },
                    )
                except Exception:
                    pass

                async def _translate_one(
                    index: int, chunk: str
                ) -> tuple[int, str | None]:
                    """Traduit un chunk avec semaphore, retourne (index, traduit|None)."""
                    async with _semaphore:
                        logger.info(
                            f"Chunk {index}/{_chunks_total} → LLM",
                            extra={
                                **log_extra,
                                "chunk_index": index,
                                "chunk_total": _chunks_total,
                            },
                        )
                        # ── Provider routing ──────────────────────
                        provider = getattr(settings, "TRANSLATION_PROVIDER", "openrouter")
                        if provider == "ollama":
                            from core.ollama import translate_srt_via_ollama
                            translated = await translate_srt_via_ollama(
                                chunk, source_lang, target_lang
                            )
                            # Fallback: if Ollama fails, try OpenRouter
                            if not translated:
                                logger.warning(
                                    f"Chunk {index}: Ollama failed, falling back to OpenRouter"
                                )
                                from core.openrouter import translate_srt as _ts
                                translated = await _ts(chunk, source_lang, target_lang)
                        else:
                            translated = await translate_srt(
                                chunk, source_lang, target_lang
                            )
                        if translated and (
                            " --> " in translated or "\n00:" in translated
                        ):
                            logger.info(
                                f"Chunk {index}/{_chunks_total} ✓ OK ({len(translated)} chars)",
                                extra={
                                    **log_extra,
                                    "chunk_index": index,
                                    "status": "ok",
                                    "chars": len(translated),
                                },
                            )
                            return index, translated
                        logger.warning(
                            f"Chunk {index}/{_chunks_total} ✗ ÉCHEC — garde original ({len(chunk)} chars)",
                            extra={
                                **log_extra,
                                "chunk_index": index,
                                "status": "fail",
                                "chars": len(chunk),
                            },
                        )
                        return index, None

                # Lancer tous les chunks en parallèle
                tasks = [_translate_one(i + 1, c) for i, c in enumerate(chunks)]
                results = await asyncio.gather(*tasks)

                # Réordonner par index et reconstruire
                results.sort(key=lambda r: r[0])
                translated_chunks: list[str] = []
                _chunk_ok = 0
                _chunk_fail = 0
                for idx, translated in results:
                    if translated:
                        translated_chunks.append(translated)
                        _chunk_ok += 1
                    else:
                        translated_chunks.append(chunks[idx - 1])  # fallback original
                        _chunk_fail += 1

                translated_srt_content = merge_srt_chunks(translated_chunks)

                logger.info(
                    f"Traduction {source_lang}→{target_lang} terminée : "
                    f"{_chunk_ok}/{_chunks_total} chunks OK, {_chunk_fail} échec(s) → "
                    f"{len(translated_srt_content)} chars total",
                    extra={
                        **log_extra,
                        "chunk_ok": _chunk_ok,
                        "chunk_fail": _chunk_fail,
                        "chunks_total": _chunks_total,
                        "total_chars": len(translated_srt_content),
                    },
                )
            else:
                _chunk_ok = 0
                _chunk_fail = 0
                _chunks_total = 0
                translated_srt_content = await translate_srt(
                    clean_srt, source_lang, target_lang
                )
                if translated_srt_content:
                    logger.info(
                        f"Traduction {source_lang}→{target_lang} OK "
                        f"({len(translated_srt_content)} chars, sans chunking)",
                        extra=log_extra,
                    )
        except Exception as e:
            logger.warning(
                "Traduction echouee, garde SRT original",
                extra={"error": str(e), **log_extra},
            )
            _chunk_ok = 0
            _chunk_fail = 0
            _chunks_total = 0
            translated_srt_content = clean_srt

    else:
        _chunk_ok = 0
        _chunk_fail = 0
        _chunks_total = 0

    srt_to_burn = translated_srt_content or clean_srt

    return StepResult(
        data={
            "translated_srt": translated_srt_content or "",
            "srt_to_burn": srt_to_burn,
            "chunks_total": _chunks_total,
            "chunk_ok": _chunk_ok,
            "chunk_fail": _chunk_fail,
            "total_chars_before": len(clean_srt) if clean_srt else 0,
            "total_chars_after": len(srt_to_burn) if srt_to_burn else 0,
            "srt_block_count": len(_parse_srt(srt_to_burn)) if srt_to_burn else 0,
        }
    )