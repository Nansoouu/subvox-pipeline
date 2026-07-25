"""
pipeline/steps/lang_metadata.py — Step 6.5 : traduit les metadonnees + highlights par langue
Stocke tout dans jobs.seo_metadata[lang] et met a jour jobs.title + jobs.seo_slug.
"""
from __future__ import annotations
import json
from core.logging_setup import get_logger
from core.openrouter import call_openrouter, PRIMARY_MODEL, OPENROUTER_URL
from core.pipeline.seo import save_seo_metadata_multilingual

logger = get_logger(__name__)

PROMPT = """You translate video metadata. Input JSON has English fields. Output same structure in {lang_name}.

Input:
{input_json}

Output ONLY JSON:
{{
  "highlights": [{{"title": "...", "summary": "..."}}],
  "slug": "auto-generated-slug-from-title"
}}"""

LANG_NAMES = {
    "en":"English","fr":"French","de":"German","es":"Spanish","pt":"Portuguese",
    "it":"Italian","nl":"Dutch","pl":"Polish","ru":"Russian","ar":"Arabic",
    "ja":"Japanese","zh":"Chinese","ko":"Korean","tr":"Turkish","hi":"Hindi",
}


async def translate_all_metadata(
    job_id: str,
    seo_metadata: dict,
    en_highlights: list[dict],
    target_langs: list[str],
    source_lang: str = "en",
) -> dict:
    """For each target lang, translate highlights + set translated title/slug."""
    if not seo_metadata:
        return {}
    if isinstance(en_highlights, (int, float)):
        en_highlights = []

    updates = {}
    for lang in target_langs:
        if lang == source_lang:
            # Source language: use English data directly
            updates[lang] = seo_metadata.get(lang, {})
            updates[lang]["highlights"] = en_highlights or []
            try:
                updates[lang]["slug"] = await _generate_slug(
                    seo_metadata.get(lang, {}).get("title", ""), job_id, lang
                )
            except Exception:
                updates[lang]["slug"] = _make_slug(seo_metadata.get(lang, {}).get("title", ""))
            continue

        # Get base SEO for this lang
        lang_seo = seo_metadata.get(lang, {})
        if not lang_seo.get("title"):
            logger.info(f"No SEO data for {lang}, skipping highlights translation")
            continue

        try:
            input_data = {
                "title": lang_seo.get("title", ""),
                "description": lang_seo.get("description", ""),
                "highlights": [{"title": h.get("title", ""), "summary": h.get("summary", "")}
                               for h in (en_highlights or [])],
            }
            if not input_data["highlights"]:
                updates[lang] = lang_seo
                updates[lang]["highlights"] = []
                continue

            result = await call_openrouter(
                model=PRIMARY_MODEL,
                api_url=OPENROUTER_URL,
                messages=[{
                    "role": "system",
                    "content": PROMPT.format(
                        lang_name=LANG_NAMES.get(lang, lang),
                        input_json=json.dumps(input_data, ensure_ascii=False),
                    ),
                }],
                temperature=0.1,
                max_tokens=2000,
                job_id=job_id,
                caller=f"translate_metadata_{lang}",
            )
            if not result:
                continue
            text = result["choices"][0]["message"]["content"]
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                text = text.rsplit("```", 1)[0]
            translated = json.loads(text)

            updates[lang] = {**lang_seo}
            updates[lang]["highlights"] = translated.get("highlights", [])
            updates[lang]["slug"] = translated.get("slug", _make_slug(lang_seo.get("title", "")))
            logger.info(f"Highlights translated for {lang}: {len(updates[lang]['highlights'])} items")

        except Exception as e:
            logger.warning(f"Metadata translation failed for {lang}: {e}")
            updates[lang] = lang_seo
            updates[lang]["highlights"] = en_highlights or []

    return updates


async def update_job_title_per_lang(job_id: str, lang: str, title: str, slug: str) -> None:
    """Update jobs.title and jobs.seo_slug with translated values."""
    try:
        from core.db import direct_connect as _direct
        from uuid import UUID
        async with _direct() as conn:
            await conn.execute(
                "UPDATE jobs SET title=$1, seo_slug=$2 WHERE id=$3",
                title, slug, UUID(job_id),
            )
    except Exception as e:
        logger.warning(f"Failed to update job title for {lang}: {e}")


def _make_slug(text: str) -> str:
    import re, unicodedata
    try:
        from unidecode import unidecode
    except ImportError:
        unidecode = lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = unidecode(text.lower())
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:80]


async def _generate_slug(title: str, job_id: str, lang: str) -> str:
    """Generate SEO slug from title using LLM for better quality."""
    import re
    if not title:
        return _make_slug(title)
    try:
        result = await call_openrouter(
            model=PRIMARY_MODEL,
            api_url=OPENROUTER_URL,
            messages=[{
                "role": "user",
                "content": f"Generate an SEO-friendly URL slug in {lang} from: {title}. Return ONLY the slug, max 80 chars, lowercase, hyphens.",
            }],
            temperature=0.1,
            max_tokens=100,
            job_id=job_id,
            caller=f"slug_{lang}",
        )
        if result:
            slug = result["choices"][0]["message"]["content"].strip().lower()
            slug = re.sub(r"[^a-z0-9-]", "", slug)
            return slug[:80]
    except Exception:
        pass
    return _make_slug(title)
