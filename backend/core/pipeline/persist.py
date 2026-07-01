"""
pipeline/persist.py — Persistance intermédiaire du pipeline — Subvox

Fournit des fonctions réutilisables pour sauvegarder et restaurer
les données intermédiaires du pipeline à chaque étape, en utilisant
les colonnes JSONB de la table jobs créées par migration_pipeline_resilience.sql.

Permet la reprise après crash worker : chaque étape vérifie si elle
a déjà été complétée avant de s'exécuter.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.logging_setup import get_logger

logger = get_logger(__name__)


# ─── Constantes ─────────────────────────────────────────────────────────────────

STEPS_ORDERED = [
    # Phase 1 - Acquisition
    "downloading",
    # Phase 2 - Transcription + Résumé rapide
    "transcribing",
    "filtering",
    "summary",                   # ← AVANCÉ : dispo dès que le transcript est propre
    # Phase 3 - Analyse enrichie (PARALLÈLE)
    "meta_analysis",             # peut tourner en parallèle avec...
    "text_analysis",             # ...text_analysis et...
    "visual_analysis",           # ...visual_analysis (asyncio.gather)
    # Phase 3b - Post-traitement analyses
    "anonymization",
    "speaker_analysis",
    "fusion",
    # Phase 4 - Traduction
    "translating",
    "segments_save",
    "ass_generation",
    "vtt_export",
    # Phase 5 - Background (non-bloquant)
    "seo",                       # ← DÉPLACÉ en dernier, non-bloquant
    "watermark",
    "burning",
    "uploading",
]

# Mapping: step_name -> (jsonb_column, description)
STEP_COLUMNS: dict[str, tuple[str, str]] = {
    "downloading": ("processed_files", "Téléchargement vidéo"),
    "meta_analysis": ("analysis_result", "Analyse métadonnées"),
    "transcribing": ("transcription_json", "Transcription audio"),
    "filtering": ("processed_steps", "Filtre hallucinations"),
    "text_analysis": ("analysis_result", "Analyse textuelle"),
    "visual_analysis": ("analysis_result", "Analyse visuelle"),
    "anonymization": ("analysis_result", "Anonymisation vidéo"),
    "speaker_analysis": ("analysis_result", "Analyse locuteurs"),
    "fusion": ("analysis_result", "Fusion analyses"),
    "seo": ("seo_metadata", "SEO Metadata"),
    "summary": ("summaries", "Résumé LLM"),
    "translating": ("translated_srt", "Traduction SRT"),
    "segments_save": ("processed_steps", "Sauvegarde segments"),
    "ass_generation": ("processed_files", "Génération ASS"),
    "vtt_export": ("processed_files", "Export VTT"),
    "watermark": ("processed_files", "Watermark"),
    "burning": ("processed_files", "Burn sous-titres"),
    "uploading": ("processed_steps", "Upload final"),
}


# ─── Helper JSONB unifié ────────────────────────────────────────────────────────


def _parse_jsonb(value: Any, label: str = "jsonb") -> dict:
    """
    Parse une valeur JSONB retournée par asyncpg.
    asyncpg peut retourner soit un dict natif, soit une string JSON à parser.
    Retourne toujours un dict (vide si parsing échoue).
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "_parse_jsonb échoué — retour dict vide",
                extra={"label": label, "error": str(exc)[:200], "raw_preview": value[:200]},
            )
            return {}
    return {}


# ─── Helpers DB ─────────────────────────────────────────────────────────────────


async def _get_job_row(job_id: str, columns: list[str]) -> dict | None:
    """Récupère une ligne jobs avec les colonnes spécifiées."""
    from core.db import direct_connect as _direct

    cols = ", ".join(columns)
    try:
        async with _direct() as conn:
            row = await conn.fetchrow(
                f"SELECT {cols} FROM jobs WHERE id=$1",
                uuid.UUID(job_id),
            )
        if row:
            return dict(row)
    except Exception as exc:
        logger.warning(
            "_get_job_row échoué",
            extra={"job_id": job_id[:8], "error": str(exc)},
        )
    return None


async def _update_job(job_id: str, **kwargs) -> bool:
    """UPDATE les colonnes spécifiées sur la table jobs."""
    from core.db import direct_connect as _direct

    if not kwargs:
        return False
    set_clauses = []
    values = []
    for i, (key, val) in enumerate(kwargs.items(), 1):
        set_clauses.append(f"{key}=${i}")
        values.append(val)
    set_clauses.append("updated_at=now()")
    values.append(uuid.UUID(job_id))

    try:
        async with _direct() as conn:
            await conn.execute(
                f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id=${len(values)}",
                *values,
            )
        return True
    except Exception as exc:
        logger.warning(
            "_update_job échoué",
            extra={"job_id": job_id[:8], "error": str(exc)},
        )
        return False


# ─── API publique ───────────────────────────────────────────────────────────────


async def get_completed_steps(job_id: str) -> set[str]:
    """
    Retourne l'ensemble des noms d'étapes déjà complétées pour ce job.
    Lit la colonne processed_steps (JSONB) qui contient
    {"step_name": "2026-04-30T03:10:00Z", ...}.

    Comportement v2 (2026-05-02) :
      - Si le job est en statut "error" : retourne les steps effectivement complétées
        (permet de relancer le pipeline partiellement)
      - Si le job est en statut "done" ET que toutes les étapes sont dans processed_steps :
        retourne toutes les étapes (job terminé, plus rien à faire)
      - Si le job est en statut "done" mais que certaines étapes sont manquantes
        (cas migration / job weird) : retourne seulement ce qui a été fait
      - Sinon : retourne les steps effectivement complétées depuis processed_steps
    """
    row = await _get_job_row(job_id, ["processed_steps", "status"])
    if not row:
        return set()

    steps: dict[str, str] = _parse_jsonb(row.get("processed_steps"), "get_completed_steps")

    # Filtrer : ne garder que les clés qui sont dans STEPS_ORDERED
    # (ignore les clés internes comme __raw_srt_lang_en, removed_llm, etc.)
    step_names = {k for k in steps.keys() if k in STEPS_ORDERED}

    # Si le job est done et que toutes les étapes sont complétées → terminé
    if row["status"] == "done" and step_names == set(STEPS_ORDERED):
        return set(STEPS_ORDERED)

    # Si le job est error ou done partiel → retourner seulement ce qui a été fait
    return step_names


async def mark_step_completed(
    job_id: str,
    step_name: str,
    extra_data: dict | None = None,
) -> bool:
    """
    Marque une étape comme complétée dans processed_steps (JSONB).
    Stocke le timestamp actuel sous la clé `step_name`.
    Si extra_data est fourni, il est fusionné dans processed_steps
    avec les clés préfixées par `__` pour éviter les collisions.
    """
    row = await _get_job_row(job_id, ["processed_steps"])
    if not row:
        return False

    ps: dict = _parse_jsonb(row.get("processed_steps"), "mark_step_completed")

    ps[step_name] = datetime.now(timezone.utc).isoformat()

    # Ajouter les données supplémentaires (préfixées par __)
    if extra_data:
        for key, val in extra_data.items():
            ps[f"__{key}"] = val

    return await _update_job(job_id, processed_steps=json.dumps(ps))


async def save_step_data(
    job_id: str,
    step_name: str,
    data: dict[str, Any],
) -> bool:
    """
    Sauvegarde des données arbitraires dans la colonne associée à cette étape
    (selon STEP_COLUMNS). Data est stocké comme JSON.

    ⚠️  FIX: Utilise json.dumps() converti en string puis
         passée comme str à _update_job. PostgreSQL stocke ça
         correctement en JSONB via asyncpg.
    """
    col_info = STEP_COLUMNS.get(step_name)
    if not col_info:
        logger.warning(
            "save_step_data: step_name inconnu",
            extra={"step_name": step_name, "job_id": job_id[:8]},
        )
        return False

    col_name, _ = col_info

    # Lire l'existant pour merge
    row = await _get_job_row(job_id, [col_name])
    if not row:
        return False

    existing: dict = _parse_jsonb(row.get(col_name), f"save_step_data.{col_name}")
    existing.update(data)

    # ✨ FIX: Passer un dict directement à asyncpg pour JSONB
    #        plutôt que json.dumps() pour éviter la double sérialisation
    return await _update_job(job_id, **{col_name: json.dumps(existing)})


async def load_step_data(
    job_id: str,
    step_name: str,
) -> dict[str, Any]:
    """
    Charge les données persistées pour une étape donnée.

    Retourne un dict avec les données de l'étape.
    """
    col_info = STEP_COLUMNS.get(step_name)
    if not col_info:
        logger.warning(
            "load_step_data: step_name inconnu",
            extra={"step_name": step_name, "job_id": job_id[:8]},
        )
        return {}

    col_name, _ = col_info
    row = await _get_job_row(job_id, [col_name])
    if not row:
        return {}

    result: dict = {}
    data = _parse_jsonb(row.get(col_name), f"load_step_data.{col_name}")

    # Logique spécifique selon le step
    if step_name == "transcribing":
        tx_json = data or {}
        # ⚠️  Flat mapping : le runner cherche tx_data.get("raw_srt") / .get("text")
        # à la racine, pas dans transcription_json. On merge les clés racines.
        for key in ("raw_srt", "text", "segments", "source_lang", "language"):
            if key in tx_json:
                result[key] = tx_json[key]
        # On garde aussi transcription_json pour rétrocompatibilité
        result["transcription_json"] = tx_json

    if step_name == "translating":
        # Priorité 1 : depuis translated_srt (colonne principale, stockée par save_step_data)
        result["translated_srt"] = data.get("translated_srt", "")
        result["srt_to_burn"] = data.get("srt_to_burn", "")
        # ✨ FIX: Vérifier aussi les clés alternatives de srt_to_burn
        if not result.get("srt_to_burn"):
            # «srt_to_burn» et «translated_srt» peuvent être inversés
            result["srt_to_burn"] = data.get("translated_srt", "")
        # Priorité 2 (renforcée) : fallback depuis processed_steps (stocké par mark_step_completed extra_data)
        if not result.get("srt_to_burn"):
            ps = _parse_jsonb(row.get("processed_steps"), "load_step_data.translating.ps")
            result["srt_to_burn"] = ps.get("__srt_to_burn", "") if ps else ""
        if not result.get("translated_srt"):
            ps = _parse_jsonb(row.get("processed_steps"), "load_step_data.translating.ps")
            result["translated_srt"] = ps.get("__translated_srt", "") if ps else ""
            if not result.get("translated_srt"):
                result["translated_srt"] = ps.get("__srt_to_burn", "") if ps else ""

    if step_name == "summary":
        result["summaries"] = data or {}

    if step_name in ("downloading", "ass_generation", "vtt_export", "watermark", "burning"):
        result["processed_files"] = data or {}
        # ⚠️  Flat mapping : le runner cherche dl_data.get("video_title") / .get("video_description")
        # à la racine, pas dans processed_files. On merge les clés racines.
        for key in ("video_title", "video_description", "source_url", "duration_s",
                     "source_lang", "width", "height", "thumbnail_url",
                     "source_storage_url", "video_type", "format", "file_size_mb",
                     "frame_rate", "watermark_url", "ass_generated", "burned_mp4_url",
                     "vtt_url", "vtt_content"):
            if key in (data or {}):
                result[key] = data[key]

    return result


async def save_pipeline_file(
    job_id: str,
    step_name: str,
    file_key: str,
    file_path: str | Path,
) -> bool:
    """
    Enregistre le chemin d'un fichier temporaire dans processed_files.
    Utile pour savoir quel fichier réutiliser lors d'une reprise.

    Exemple :
        save_pipeline_file(job_id, "downloading", "source_mp4", "/tmp/x/source.mp4")
    """
    return await save_step_data(
        job_id,
        step_name,
        {file_key: str(file_path)},
    )


async def save_summary(
    job_id: str,
    lang: str,
    text: str,
) -> bool:
    """Sauvegarde un résumé dans la colonne summaries (JSONB)."""
    row = await _get_job_row(job_id, ["summaries"])
    if not row:
        return False

    summaries: dict = _parse_jsonb(row.get("summaries"), "save_summary")
    summaries[lang] = text
    return await _update_job(job_id, summaries=json.dumps(summaries))


async def get_vtt_url(job_id: str) -> str:
    """
    Récupère l'URL VTT depuis processed_steps (clé __vtt_url).
    Avec fallback vers le bucket Supabase si la clé n'existe pas.

    Retourne une chaîne vide si aucun VTT n'est trouvé.
    """
    row = await _get_job_row(job_id, ["processed_steps", "target_lang", "source_lang", "created_at"])
    if not row:
        return ""

    ps = _parse_jsonb(row.get("processed_steps"), "get_vtt_url")

    # Priorité 1 : clé directe
    vtt_url = ps.get("__vtt_url", "")

    # Priorité 2 : clé par langue (target_lang)
    if not vtt_url:
        target_lang = row.get("target_lang")
        if target_lang:
            vtt_url = ps.get(f"__vtt_url_{target_lang}", "")

    # Priorité 3 : clé source_lang
    if not vtt_url:
        source_lang = row.get("source_lang")
        if source_lang:
            vtt_url = ps.get(f"__vtt_url_{source_lang}", "")

    return vtt_url


async def get_vtt_urls(
    job_id: str,
) -> dict[str, str]:
    """
    Récupère les URLs VTT (traduit + source) depuis processed_steps.
    Avec fallback vers le bucket Supabase si les clés n'existent pas.

    Retourne un dict avec les clés "vtt_url" et "vtt_source_url".
    """
    row = await _get_job_row(job_id, [
        "processed_steps", "processed_files", "target_lang", "source_lang", "created_at"
    ])
    if not row:
        return {"vtt_url": "", "vtt_source_url": ""}

    ps = _parse_jsonb(row.get("processed_steps"), "get_vtt_urls.ps")
    pf = _parse_jsonb(row.get("processed_files"), "get_vtt_urls.pf")

    target_lang = row.get("target_lang") or ""
    source_lang = row.get("source_lang") or ""

    # ── Priorité 1 : clés dans processed_steps par langue ──
    vtt_url = ps.get(f"__vtt_url_{target_lang}") if target_lang else None
    vtt_source_url = ps.get(f"__vtt_source_url_{source_lang}") if source_lang else None

    # ── Priorité 2 : clés globales dans processed_steps ──
    if not vtt_url:
        vtt_url = ps.get("__vtt_url", "")
    if not vtt_source_url:
        vtt_source_url = ps.get("__vtt_source_url", "")

    # ── Priorité 3 : clés dans processed_files ──
    if not vtt_url:
        vtt_url = pf.get("vtt_url", "")
    if not vtt_source_url:
        vtt_source_url = pf.get("vtt_source_url", "")

    # ── Priorité 4 : Supabase fallback ──
    if not vtt_url:
        created = row.get("created_at")
        if created:
            vtt_url = _fallback_vtt_url(job_id, target_lang, created)
    if not vtt_source_url:
        created = row.get("created_at")
        if created and source_lang:
            vtt_source_url = _fallback_vtt_url(job_id, source_lang, created, source=True)

    return {"vtt_url": vtt_url or "", "vtt_source_url": vtt_source_url or ""}


def _fallback_vtt_url(
    job_id: str,
    lang: str,
    created_at: datetime,
    source: bool = False,
) -> str:
    """
    Construit URL VTT fallback depuis Supabase Storage.
    Format: /storage/v1/object/public/translated-videos/videos/{date}/{job_id}/subtitles_{job_id}_{lang}.vtt
    """
    from core.config import settings

    date_str = created_at.strftime("%Y/%m/%d")
    prefix = "subtitles_source" if source else "subtitles"
    return (
        f"{settings.supabase_url or 'https://xfioatyrurzxwttojlpg.supabase.co'}"
        f"/storage/v1/object/public/translated-videos/videos/{date_str}/{job_id}/{prefix}_{job_id}_{lang}.vtt"
    )


# ─── Summary helpers ────────────────────────────────────────────────────────────


async def save_step_summary(
    job_id: str,
    lang: str,
    summary_data: dict,
) -> bool:
    """
    Sauvegarde le résumé structuré (summary + moments + hook + catégorie)
    dans la colonne summaries (JSONB) pour une langue donnée.

    summary_data doit contenir les clés : summary, moments, hook, category, summary_lang
    """
    row = await _get_job_row(job_id, ["summaries"])
    if not row:
        return False

    summaries: dict = _parse_jsonb(row.get("summaries"), "save_step_summary")
    summaries[lang] = summary_data

    # Marquer comme complet
    summaries["_status"] = "COMPLETE"

    return await _update_job(job_id, summaries=json.dumps(summaries))


async def get_summary_for_lang(
    job_id: str,
    lang: str,
) -> str | None:
    """
    Récupère le résumé pour une langue spécifique.
    Retourne None si pas encore généré.
    """
    data = await load_step_data(job_id, "summary")
    if not data:
        return None
    summaries = data.get("summaries", {})
    lang_data = summaries.get(lang)
    if isinstance(lang_data, dict):
        return lang_data.get("text") or lang_data.get("summary", "")
    if isinstance(lang_data, str):
        return lang_data
    return None


# ─── Filtered SRT helpers ───────────────────────────────────────────────────────


async def save_filtered_data(
    job_id: str,
    filtered_srt: str,
    hallucination_stats: dict | None = None,
    source_lang: str = "",
) -> bool:
    """Sauvegarde les données filtrées (SRT + stats)."""
    extra = {}
    if filtered_srt:
        extra["filtered_srt"] = filtered_srt
        if source_lang:
            extra[f"raw_srt_lang_{source_lang}_filtered"] = filtered_srt
    if hallucination_stats:
        extra["hallucination_stats"] = hallucination_stats

    return await mark_step_completed(job_id, "filtering", extra_data=extra)


async def save_filtered_srt(
    job_id: str,
    filtered_srt: str,
    source_lang: str = "",
) -> bool:
    """Wrapper vers save_filtered_data — utilisé par runner.py.

    Sauvegarde le SRT filtré dans processed_steps (clé __filtered_srt
    et __raw_srt_lang_{source_lang}_filtered).
    """
    return await save_filtered_data(
        job_id, filtered_srt, source_lang=source_lang,
    )


async def load_filtered_srt(
    job_id: str,
    source_lang: str = "",
) -> str:
    """Charge le SRT filtré depuis processed_steps.

    Cherche par ordre de priorité :
    1. __raw_srt_lang_{source_lang}_filtered
    2. __filtered_srt

    Retourne une chaîne vide si aucun SRT filtré n'est trouvé.
    """
    row = await _get_job_row(job_id, ["processed_steps"])
    if not row:
        return ""

    ps = _parse_jsonb(row.get("processed_steps"), "load_filtered_srt")

    # Priorité 1 : clé par langue
    if source_lang:
        lang_key = f"__raw_srt_lang_{source_lang}_filtered"
        if lang_key in ps:
            return ps[lang_key]

    # Priorité 2 : clé générique
    return ps.get("__filtered_srt", "")


# ─── Resume / Error helpers ────────────────────────────────────────────────────


async def increment_resume_attempts(job_id: str) -> int:
    """Incrémente le compteur de tentatives de reprise dans processed_steps.

    Stocké sous la clé __resume_attempts.
    Retourne le nombre de tentatives après incrémentation.
    """
    row = await _get_job_row(job_id, ["processed_steps"])
    if not row:
        return 1

    ps = _parse_jsonb(row.get("processed_steps"), "increment_resume_attempts")

    attempts = int(ps.get("__resume_attempts", 0)) + 1
    ps["__resume_attempts"] = attempts

    await _update_job(job_id, processed_steps=json.dumps(ps))
    return attempts


async def set_error_context(
    job_id: str,
    context_type: str,
    error_message: str,
    completed_steps: list | None = None,
    is_resume: bool = False,
) -> bool:
    """Sauvegarde le contexte d'erreur dans processed_steps.

    Stocke les clés __last_error, __error_step, __error_completed_steps,
    __error_is_resume et __error_timestamp.
    """
    extra = {
        "last_error": error_message,
        "error_step": context_type,
        "error_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if completed_steps is not None:
        extra["error_completed_steps"] = completed_steps
    if is_resume:
        extra["error_is_resume"] = True

    return await mark_step_completed(job_id, context_type, extra_data=extra)


async def get_source_mp4_path(job_id: str) -> str | None:
    """Retourne le chemin du fichier source.mp4 depuis processed_files."""
    data = await load_step_data(job_id, "downloading")
    pf = data.get("processed_files", {})
    return pf.get("source_mp4")


async def save_watermark_settings(
    job_id: str,
    watermark_png: str,
    watermark_text: str = "",
) -> bool:
    """Sauvegarde les paramètres de watermark."""
    extra = {}
    if watermark_text:
        extra["watermark_text"] = watermark_text
    if watermark_png:
        extra["watermark_png_path"] = watermark_png

    return await save_step_data(
        job_id,
        "watermark",
        {"watermark_png": watermark_png, "watermark_text": watermark_text},
    )


async def save_vtt_urls(
    job_id: str,
    vtt_url: str,
    vtt_source_url: str,
    target_lang: str,
    source_lang: str,
) -> bool:
    """
    Sauvegarde les URLs VTT dans processed_steps + processed_files.
    Stocke :
    - processed_steps.__vtt_url (global)
    - processed_steps.__vtt_url_{target_lang} (par langue cible)
    - processed_steps.__vtt_url_{source_lang} (par langue source)
    - processed_steps.__vtt_source_url
    - processed_steps.__vtt_source_url_{source_lang}
    - processed_files.vtt_url (pour rétrocompatibilité)

    NOTE : Cette fonction est conçue pour être appelée PARTOUT où des VTT
    sont persistés (runner, steps, etc.) pour garantir une cohérence multi-langue.
    """
    extra = {
        "vtt_url": vtt_url,
        "vtt_source_url": vtt_source_url,
    }
    if target_lang:
        extra[f"vtt_url_{target_lang}"] = vtt_url
    if source_lang:
        extra[f"vtt_url_{source_lang}"] = vtt_url
        extra[f"vtt_source_url_{source_lang}"] = vtt_source_url

    ok1 = await mark_step_completed(job_id, "vtt_export", extra_data=extra)

    ok2 = await save_step_data(
        job_id,
        "vtt_export",
        {"vtt_url": vtt_url, "vtt_source_url": vtt_source_url},
    )

    return ok1 and ok2


# ─── Burn asynchrone — status helpers ───────────────────────────────────────


async def save_burn_status(
    job_id: str,
    status: str,
    progress_pct: int = 0,
    storage_url: str = "",
) -> bool:
    """
    Sauvegarde l'état du burn asynchrone dans processed_steps.
    
    Status: null | "pending" | "burning" | "watermarking" | "uploading" | "ready" | "error"
    
    Stocké sous les clés :
    - __burn_status
    - __burn_progress (0-100)
    - __burned_url (final url quand ready)
    """
    extra = {
        "burn_status": status,
        "burn_progress": progress_pct,
    }
    if storage_url:
        extra["burned_url"] = storage_url
    
    return await mark_step_completed(job_id, f"__burn_{status}", extra_data=extra)


async def get_burn_status(job_id: str) -> dict:
    """
    Récupère l'état du burn asynchrone depuis processed_steps.
    
    Retourne : {status, progress_pct, storage_url, error?}
    """
    row = await _get_job_row(job_id, ["processed_steps", "storage_url", "source_storage_url"])
    if not row:
        return {"status": None, "progress_pct": 0, "storage_url": "", "burned_url": ""}
    
    ps = _parse_jsonb(row.get("processed_steps"), "get_burn_status")
    storage_url = row.get("storage_url") or ""
    row.get("source_storage_url") or ""
    
    # Lire depuis processed_steps (ne pas utiliser storage_url != source_storage_url
    # car c'est vrai pour toute vidéo traduite, même sans burn)
    burn_status = ps.get("__burn_status")
    burn_progress = int(ps.get("__burn_progress", 0))
    burned_url = ps.get("__burned_url", "")
    
    # Fallback : si le burnt status est "burning" mais que la clé n'existe pas -> pending
    if not burn_status:
        return {"status": None, "progress_pct": 0, "storage_url": storage_url, "burned_url": ""}
    
    result = {
        "status": burn_status,
        "progress_pct": burn_progress,
        "storage_url": storage_url,
        "burned_url": burned_url,
    }
    
    # Si ready mais pas de storage_url mis à jour, le renvoyer quand même
    if burn_status == "ready" and burned_url and not storage_url:
        result["storage_url"] = burned_url
    
    return result