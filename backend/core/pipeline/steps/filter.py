"""
Étape 3 : Filtre des hallucinations (regex + LLM).

Produit une sortie JSON structurée avec segments, confiance, stats.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.srt import _parse_srt
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_filter(
    job_id: str,
    srt_raw: str = "",
    transcript_tx: str = "",
    segments_json: list[dict] | None = None,
) -> StepResult:
    """
    Filtre les hallucinations (regex + LLM) du SRT brut.

    segments_json : liste optionnelle de segments structurés issus de Groq
                    (avec confidence, no_speech_prob, etc.)
                    Si fournie, le filtre peut utiliser la confiance par segment.

    Retourne un StepResult.data contenant :
      {
        "raw_srt": str,           # SRT filtré (rétrocompatibilité)
        "segments": [             # Segments structurés filtrés
          {"index": int, "start_s": float, "end_s": float, "text": str,
           "confidence": float, "no_speech_prob": float, "language": str,
           "is_hallucination": bool, "filter_reason": str}
        ],
        "removed_regex": int,     # Nb supprimés par regex
        "removed_llm": int,       # Nb supprimés par LLM (future)
        "total_input": int,       # Nb segments avant filtre
        "total_output": int,      # Nb segments après filtre
        "avg_confidence": float,  # Confiance moyenne des segments conservés
      }
    """
    from core.whisper_hallucination_filter import (
        apply_llm_hallucination_filter,
        is_hallucination,
    )

    log_extra = {"job_id": job_id}

    # ── 1. Charger les segments ──────────────────────────────────────────────
    if not srt_raw:
        tmp = _get_tmp(job_id)
        srt_path = tmp / "transcript.srt"
        if srt_path.exists():
            srt_raw = srt_path.read_text(encoding="utf-8")

    # Si on a des segments structurés, on les utilise (plus riches)
    # Sinon, on parse le SRT brut (rétrocompatibilité)
    if segments_json:
        raw_segments: list[dict] = list(segments_json)
    else:
        blocks = _parse_srt(srt_raw)
        raw_segments = []
        for i, b in enumerate(blocks, 1):
            raw_segments.append({
                "index": i,
                "start_s": 0.0,
                "end_s": 0.0,
                "text": b.get("text", "").strip(),
                "confidence": 0.0,
                "no_speech_prob": 1.0,
                "language": "",
                "is_hallucination": False,
                "filter_reason": "",
            })

    total_input = len(raw_segments)
    removed_regex = 0

    # ── 2. Filtrage regex ────────────────────────────────────────────────────
    filtered_segments: list[dict] = []
    for seg in raw_segments:
        text = seg.get("text", "").strip()
        if not text:
            removed_regex += 1
            continue

        # Détection d'hallucination
        if is_hallucination(text):
            seg["is_hallucination"] = True
            seg["filter_reason"] = "regex"
            removed_regex += 1
            continue

        # Faible confiance (si dispo) — seuil : avg_logprob < -1.0 = suspect
        confidence = seg.get("confidence", 0.0)
        if confidence < -1.0 and len(text.split()) <= 3:
            seg["is_hallucination"] = True
            seg["filter_reason"] = "low_confidence"
            removed_regex += 1
            continue

        # no_speech_prob élevé = probablement bruit
        no_speech = seg.get("no_speech_prob", 0.0)
        if no_speech > 0.8 and len(text.split()) <= 2:
            seg["is_hallucination"] = True
            seg["filter_reason"] = "no_speech"
            removed_regex += 1
            continue

        seg["is_hallucination"] = False
        seg["filter_reason"] = ""
        filtered_segments.append(seg)

    # Garde-fou : si tous les segments ont été filtrés, on garde l'original
    if not filtered_segments and srt_raw:
        logger.warning(
            "Tous les segments filtrés — garde SRT original",
            extra=log_extra,
        )
        filtered_segments = raw_segments
        removed_regex = 0

    # ── 3. Filtrage LLM (future) ────────────────────────────────────────────
    removed_llm = 0
    try:
        blocks_for_llm = [
            {"index": s["index"], "text": s["text"]}
            for s in filtered_segments
        ]
        removed_llm, _no_audio = await apply_llm_hallucination_filter(
            blocks_for_llm, transcript_tx
        )
        if removed_llm > 0:
            # Marquer les segments supprimés par LLM
            _keep_indices = {
                s["index"] for s in filtered_segments[:-removed_llm]
                if removed_llm > 0
            }
            # Note: l'implémentation LLM actuelle est un placeholder (retourne 0)
    except Exception as e:
        logger.warning(
            "Filtre hallucination LLM ignoré",
            extra={"error": str(e), **log_extra},
        )

    # ── 4. Construction de la sortie ─────────────────────────────────────────
    total_output = len(filtered_segments)
    avg_confidence = (
        round(
            sum(s.get("confidence", 0) for s in filtered_segments) / max(total_output, 1),
            4,
        )
        if filtered_segments
        else 0.0
    )

    # Générer le SRT final (rétrocompatibilité pour les étapes suivantes)
    clean_srt = _build_srt_from_segments(filtered_segments) if filtered_segments else srt_raw

    tmp = _get_tmp(job_id)
    srt_path = tmp / "transcript.srt"
    srt_path.write_text(clean_srt, encoding="utf-8")

    return StepResult(
        data={
            "raw_srt": clean_srt,
            "segments": filtered_segments,
            "removed_regex": removed_regex,
            "removed_llm": removed_llm,
            "total_input": total_input,
            "total_output": total_output,
            "avg_confidence": avg_confidence,
        },
        files={"srt_path": str(srt_path)},
    )


def _build_srt_from_segments(segments: list[dict]) -> str:
    """Reconstruit un SRT depuis une liste de segments structurés."""
    from core.pipeline.srt import _to_srt_time

    lines = []
    for seg in segments:
        if not seg.get("text", "").strip():
            continue
        start = _to_srt_time(seg.get("start_s", 0))
        end = _to_srt_time(seg.get("end_s", seg.get("start_s", 0) + 2))
        text = seg["text"]
        lines.append(f"{seg.get('index', 1)}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)
