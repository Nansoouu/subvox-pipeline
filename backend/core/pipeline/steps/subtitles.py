"""
Étape 7 : Génération ASS et export VTT.
"""

from __future__ import annotations

import os
import re as _re
from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import (
    _get_video_dims,
)
from core.pipeline.srt import (
    _parse_srt,
    _srt_to_ass,
)
from core.subtitle_splitter import split_srt_advanced
from core.pipeline.duration_tiers import DurationTier
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


# ─── Étape 7 : Génération ASS ─────────────────────────────────────────────────


async def step_ass_generation(
    job_id: str,
    srt_to_burn: str = "",
    source_srt: str = "",
    params_override: dict | None = None,
    duration_tier: DurationTier | None = None,
    source_path_override: str = "",
) -> StepResult:
    """
    Génère le fichier ASS (sous-titres stylisés) à partir du SRT.
    """
    tmp = _get_tmp(job_id)
    tmp.mkdir(parents=True, exist_ok=True)
    source_path = Path(source_path_override) if source_path_override else tmp / "source.mp4"

    if not source_path.exists():
        raise RuntimeError("Fichier source introuvable pour generation ASS")

    if not srt_to_burn:
        logger.warning(
            "srt_to_burn vide — fallback rechargement SRT depuis DB",
            extra={"job_id": job_id},
        )
        # Fallback : recharger le SRT filtré depuis la DB
        try:
            from core.pipeline.persist import load_step_data as _load_ps, load_filtered_srt as _load_fs
            filter_data = await _load_ps(job_id, "filtering")
            if filter_data and filter_data.get("raw_srt"):
                srt_to_burn = filter_data["raw_srt"]
                logger.info(
                    "Fallback SRT rechargé depuis filtering (raw_srt)",
                    extra={"job_id": job_id, "len": len(srt_to_burn)},
                )
            if not srt_to_burn:
                tx_data = await _load_ps(job_id, "transcribing")
                if tx_data and tx_data.get("raw_srt"):
                    srt_to_burn = tx_data["raw_srt"]
                    logger.info(
                        "Fallback SRT rechargé depuis transcribing (raw_srt)",
                        extra={"job_id": job_id, "len": len(srt_to_burn)},
                    )
            if not srt_to_burn:
                source_lang = ""
                dl_data = await _load_ps(job_id, "downloading")
                if dl_data:
                    source_lang = dl_data.get("source_lang", "")
                srt_to_burn = await _load_fs(job_id, source_lang)
                if srt_to_burn:
                    logger.info(
                        "Fallback SRT rechargé depuis load_filtered_srt",
                        extra={"job_id": job_id, "len": len(srt_to_burn)},
                    )
        except Exception as exc:
            logger.warning(
                "Fallback SRT échoué",
                extra={"job_id": job_id, "error": str(exc)},
            )

    if not srt_to_burn:
        raise RuntimeError(
            "srt_to_burn vide pour generation ASS -- aucun SRT traduit disponible"
        )

    _params_override = params_override or {}

    max_words_default = int(os.environ.get("SUBTITLE_MAX_WORDS_PER_SEGMENT", "15"))
    max_words = _params_override.get("max_words", max_words_default)
    vid_w, vid_h = _get_video_dims(source_path)
    if max_words > 0:
        original_len = len(srt_to_burn)
        min_dur = duration_tier.subsegment_min_duration_s if duration_tier else float(
            os.environ.get("SUBTITLE_MIN_DURATION", "0.8")
        )
        min_seg_dur = duration_tier.min_segment_duration_s if duration_tier else float(
            os.environ.get("SUBTITLE_MIN_SEGMENT_DURATION", "0.5")
        )
        srt_to_burn = split_srt_advanced(
            srt_to_burn,
            resolution=(vid_w, vid_h),
            min_duration_s=min_dur,
            min_segment_duration_s=min_seg_dur,
            max_gap_s=float(os.environ.get("SUBTITLE_MAX_GAP", "0.03")),
            overlap_s=float(os.environ.get("SUBTITLE_OVERLAP", "0.05")),
        )
        if len(srt_to_burn) != original_len:
            logger.info(
                f"Segments decoupes par resolution ({vid_w}x{vid_h})",
                extra={
                    "job_id": job_id,
                    "original_chars": original_len,
                    "new_chars": len(srt_to_burn),
                },
            )

    ass_path = tmp / "subtitles.ass"
    ass_content = _srt_to_ass(
        srt_to_burn,
        vid_w=vid_w,
        vid_h=vid_h,
    )
    ass_path.write_text(ass_content, encoding="utf-8")

    ass_lines_count = ass_content.count("Dialogue:")
    ass_size_kb = (
        round(ass_path.stat().st_size / 1024.0, 2) if ass_path.exists() else 0.0
    )

    # Génération du ASS source (langue d'origine) si disponible
    source_ass_path = ""
    source_ass_lines = 0
    if source_srt.strip():
        source_ass_path = tmp / "source_subtitles.ass"
        source_ass_content = _srt_to_ass(
            source_srt,
            vid_w=vid_w,
            vid_h=vid_h,
        )
        source_ass_path.write_text(source_ass_content, encoding="utf-8")
        source_ass_lines = source_ass_content.count("Dialogue:")

    _word_split_applied = max_words > 0
    _segments_before = (
        len(_parse_srt(srt_to_burn if max_words > 0 else ""))
        if max_words > 0
        else ass_lines_count
    )

    files = {"ass_path": str(ass_path)}
    if source_ass_path:
        files["source_ass_path"] = str(source_ass_path)

    return StepResult(
        files=files,
        data={
            "ass_chars": len(ass_content),
            "total_lines": ass_lines_count,
            "font_size": 14,
            "ass_file_size_kb": ass_size_kb,
            "mode": "ass",
            "word_split_applied": _word_split_applied,
            "source_ass_lines": source_ass_lines,
        },
    )


# ─── Helpers VTT ──────────────────────────────────────────────────────────────


def _srt_content_to_vtt(srt_content: str) -> str:
    """
    Convertit un contenu SRT en WebVTT.
    """
    vtt_lines = ["WEBVTT", ""]
    in_body = False
    for line in srt_content.splitlines():
        line = _re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", line)
        if " --> " in line:
            in_body = True
            vtt_lines.append(line)
        elif in_body and line.strip():
            vtt_lines.append(line)
        elif in_body and not line.strip():
            vtt_lines.append("")
            in_body = False
    return "\n".join(vtt_lines)


def _ass_ts_to_vtt(ts: str) -> str:
    """Convertit un timestamp ASS (H:MM:SS.cs) en WebVTT (HH:MM:SS.mmm)."""
    h, m, rest = ts.split(":")
    s, cs = rest.split(".")
    cs = int(cs) * 10  # centiseconds → milliseconds
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{cs:03d}"


# ─── Étape 8 : Export VTT ─────────────────────────────────────────────────────


async def step_vtt_export(
    job_id: str,
    raw_srt: str = "",
    target_lang: str = "",
) -> StepResult:
    """
    Convertit le fichier ASS en WebVTT pour l'affichage overlay.
    Upload le VTT (traduit) vers Supabase Storage.
    """
    from core.supabase_storage import upload_text as _upload_text

    log_extra = {"job_id": job_id}
    tmp = _get_tmp(job_id)
    ass_path = tmp / "subtitles.ass"
    vtt_path = tmp / "subtitles.vtt"

    lang_suffix = f"_{target_lang}" if target_lang else ""
    lang_suffix_source = lang_suffix

    if not ass_path.exists():
        logger.warning(
            "Fichier ASS introuvable pour export VTT — skip",
            extra=log_extra,
        )
        return StepResult(data={"vtt_exported": False, "reason": "no_ass"})

    ass_content = ass_path.read_text(encoding="utf-8")

    # Convertir ASS → WebVTT
    vtt_lines = ["WEBVTT", ""]
    for line in ass_content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            start_ass = parts[1].strip()
            end_ass = parts[2].strip()
            text = parts[9].strip()

            # Nettoyer les balises ASS
            text = text.replace("\\N", "\n").replace("\\n", "\n")
            text = text.replace("{\\i1}", "<i>").replace("{\\i0}", "</i>")
            text = text.replace("{\\b1}", "<b>").replace("{\\b0}", "</b>")
            text = _re.sub(r"\{\\[^}]+\}", "", text)
            text = _re.sub(r"\{\\}", "", text)

            start_vtt = _ass_ts_to_vtt(start_ass)
            end_vtt = _ass_ts_to_vtt(end_ass)

            vtt_lines.append(f"{start_vtt} --> {end_vtt}")
            vtt_lines.append(text)
            vtt_lines.append("")

    vtt_content = "\n".join(vtt_lines)
    vtt_path.write_text(vtt_content, encoding="utf-8")

    vtt_size_kb = (
        round(vtt_path.stat().st_size / 1024.0, 2) if vtt_path.exists() else 0.0
    )
    vtt_total_cues = vtt_content.count("-->")

    logger.info(
        f"VTT traduit exporte: {vtt_total_cues} cues, {vtt_size_kb}KB",
        extra=log_extra,
    )

    vtt_filename = f"subtitles_{job_id}{lang_suffix}.vtt"
    vtt_url = ""
    try:
        upload_res = await _upload_text(
            job_id,
            vtt_content,
            filename=vtt_filename,
            content_type="text/vtt",
        )
        if upload_res:
            vtt_url = upload_res["storage_url"]
            logger.info(
                f"VTT traduit uploade: {vtt_url[:80]}",
                extra=log_extra,
            )
    except Exception as e:
        logger.error(f"Upload VTT traduit echoue: {e}", extra=log_extra)

    # VTT source
    vtt_source_url = ""
    vtt_source_total_cues = 0
    vtt_source_size_kb = 0.0

    if raw_srt:
        try:
            vtt_source_content = _srt_content_to_vtt(raw_srt)
            vtt_source_path = tmp / "subtitles_source.vtt"
            vtt_source_path.write_text(vtt_source_content, encoding="utf-8")
            vtt_source_total_cues = vtt_source_content.count("-->")
            vtt_source_size_kb = (
                round(vtt_source_path.stat().st_size / 1024.0, 2)
                if vtt_source_path.exists()
                else 0.0
            )

            vtt_source_filename = f"subtitles_source_{job_id}{lang_suffix_source}.vtt"
            upload_source = await _upload_text(
                job_id,
                vtt_source_content,
                filename=vtt_source_filename,
                content_type="text/vtt",
            )
            if upload_source:
                vtt_source_url = upload_source["storage_url"]
                logger.info(
                    f"VTT source uploade: {vtt_source_url[:80]} "
                    f"({vtt_source_total_cues} cues, {vtt_source_size_kb}KB)",
                    extra=log_extra,
                )
        except Exception as e:
            logger.error(f"Upload VTT source echoue: {e}", extra=log_extra)

    return StepResult(
        files={
            "vtt_path": str(vtt_path),
            "vtt_url": vtt_url,
            "vtt_source_url": vtt_source_url,
        },
        data={
            "vtt_exported": True,
            "vtt_total_cues": vtt_total_cues,
            "vtt_size_kb": vtt_size_kb,
            "vtt_url": vtt_url,
            "vtt_source_url": vtt_source_url,
            "vtt_source_total_cues": vtt_source_total_cues,
            "vtt_source_size_kb": vtt_source_size_kb,
            "target_lang": target_lang,
        },
    )