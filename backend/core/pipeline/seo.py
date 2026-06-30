"""
pipeline/seo.py — SEO Metadata Generation — Subvox

SeoStep : genere les metadonnees SEO optimisees (titre, description, H1, keywords)
pour la langue cible (et la langue source) d'un job de traduction video.

Stockage : jobs.seo_metadata (JSONB multilingue)
Slug : jobs.seo_slug (TEXT UNIQUE, format {titre-nettoye}-{DD-MM-YYYY})
Anti-doublon : pg_trgm.similarity() sur les titres de meme categorie

Refacto v2 : generate_seo_all_langs() genere le SEO pour les 21 langues
en un seul appel LLM (au lieu de 21 appels individuels).
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from core.config import settings
from core.logging_setup import get_logger
from core.openrouter import call_openrouter, PRIMARY_MODEL, _estimate_cost

logger = get_logger(__name__)

# Constantes SEO
TITLE_MIN_CHARS = 40
TITLE_MAX_CHARS = 60
DESC_MIN_CHARS = 120
DESC_MAX_CHARS = 155
H1_MAX_CHARS = 70
KEYWORDS_MIN = 5
KEYWORDS_MAX = 10

_seen_titles: set[str] = set()

# Stop words par langue (mots vides a retirer du slug)
FR_STOP_WORDS = {
    "le", "la", "de", "un", "une", "des", "pour", "et", "ou", "en", "du",
    "au", "aux", "ce", "cette", "les", "mon", "ton", "son", "leur", "nos",
    "vos", "ses", "sur", "dans", "avec", "par", "est", "sont", "que", "qui",
    "donc", "mais", "car", "ni", "ne", "pas", "plus", "très", "tout", "tous",
    "toute", "toutes", "peut", "peu", "aussi", "comme", "sans", "chez",
    "vers", "depuis", "pendant", "avant", "apres", "entre", "sous", "chaque",
    "quel", "quelle", "quels", "quelles", "comment", "pourquoi", "quand",
}

EN_STOP_WORDS = {
    "the", "a", "an", "of", "for", "and", "or", "in", "on", "at", "to",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "need", "dare", "ought", "used", "this", "that", "these",
    "those", "it", "its", "my", "your", "his", "her", "our", "their",
    "with", "without", "from", "by", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just",
}

ES_STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "para", "por", "y", "e", "o", "u", "en", "con", "sin", "sobre",
    "entre", "hasta", "desde", "al", "que", "es", "son", "se", "su",
    "sus", "tu", "mi", "nos", "os", "les", "le", "lo", "como", "mas",
    "pero", "sino", "tambien", "muy", "todo", "cada", "este", "esta",
}

DE_STOP_WORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer",
    "eines", "einem", "einen", "und", "oder", "aber", "mit", "von",
    "zu", "auf", "für", "an", "aus", "bei", "nach", "vor", "durch",
    "über", "um", "nicht", "auch", "noch", "schon", "nur", "sehr",
    "alle", "diese", "dieser", "dieses", "sie", "er", "es", "wir",
    "ihr", "sich", "bin", "bist", "ist", "sind", "seid", "war",
    "waren", "wird", "werden", "hat", "haben", "kann", "können",
    "muss", "müssen", "soll", "sollen", "will", "wollen",
}

# Aggregation des stop words par langue
STOP_WORDS_MAP = {
    "fr": FR_STOP_WORDS,
    "en": EN_STOP_WORDS,
    "es": ES_STOP_WORDS,
    "de": DE_STOP_WORDS,
}


def _clean_stop_words(title: str, lang: str = "fr") -> str:
    """Retire les stop words d'un titre selon la langue."""
    stop_words = STOP_WORDS_MAP.get(lang[:2], FR_STOP_WORDS)
    words = title.lower().split()
    cleaned = [w for w in words if w not in stop_words and len(w) > 1]
    return " ".join(cleaned)


def _slugify(text: str) -> str:
    """
    Convertit un texte en slug lisible pour URL.
    - lowercase
    - remplace accents
    - garde uniquement [a-z0-9-]
    - remplace les espaces par des tirets
    """
    # Normaliser Unicode (separer accents des lettres)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Remplacer les caracteres non alphanumeriques (sauf tiret) par un espace
    text = re.sub(r"[^a-z0-9\s-]", " ", text)

    # Remplacer les espaces multiples par un tiret
    text = re.sub(r"\s+", "-", text.strip())

    # Supprimer les tirets multiples et en debut/fin
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-")

    return text


def _title_to_slug(title: str, lang: str = "fr", created_at: str | None = None) -> str:
    """
    Genere un slug lisible unique a partir du titre SEO.
    Format : {titre-nettoye-sans-stop-words}-{DD-MM-YYYY}

    1. Nettoie les stop words
    2. Slugify
    3. Ajoute la date
    """
    if not title:
        return ""

    # Utiliser la date du jour si non fournie
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    date_str = dt.strftime("%d-%m-%Y")

    # Nettoyer les stop words dans la langue du job
    clean_title = _clean_stop_words(title, lang)

    # Si apres nettoyage il ne reste rien, utiliser le titre original
    if not clean_title:
        clean_title = title

    # Slugify
    slug = _slugify(clean_title)

    # Limiter a 80 caracteres
    if len(slug) > 60:
        slug = slug[:60].rstrip("-")

    # Ajouter la date
    slug = f"{slug}-{date_str}"

    return slug


def _get_unique_slug(base_slug: str, job_id: str, existing_slugs: set[str]) -> str:
    """Garantit l'unicite du slug en ajoutant un suffixe si necessaire."""
    if base_slug not in existing_slugs:
        return base_slug

    # Ajouter un suffixe court
    suffix = str(uuid.uuid4())[:4].upper()
    unique_slug = f"{base_slug}-{suffix}"
    return unique_slug


async def _find_similar_titles(
    title: str,
    category: str,
    lang: str,
    job_id: str,
    threshold: float = 0.4,
    limit: int = 5,
) -> list[dict]:
    """
    Recherche des titres similaires dans la meme categorie/langue
    via pg_trgm.similarity().

    threshold : seuil de similarite (0.0 a 1.0, defaut 0.4)
    limit : nombre max de resultats (defaut 5)
    Retourne : liste de dicts {"title": str, "job_id": str, "similarity": float}
    """
    if not title:
        return []

    try:
        from core.db import direct_connect as _direct
        from uuid import UUID

        async with _direct() as conn:
            rows = await conn.fetch(
                """
                SELECT id, seo_metadata->$2->>'title' AS seo_title,
                       similarity(COALESCE(seo_metadata->$2->>'title', ''), $1) AS sim
                FROM jobs
                WHERE category = $3
                  AND id != $4
                  AND seo_metadata ? $2
                  AND seo_metadata->$2->>'title' IS NOT NULL
                  AND seo_metadata->$2->>'title' != ''
                  AND similarity(COALESCE(seo_metadata->$2->>'title', ''), $1) > $5
                ORDER BY sim DESC
                LIMIT $6
                """,
                title,
                lang,
                category or "",
                UUID(job_id),
                threshold,
                limit,
            )

            results = []
            for r in rows:
                seo_title = r["seo_title"]
                if seo_title:
                    results.append({
                        "title": seo_title,
                        "job_id": str(r["id"]),
                        "similarity": round(float(r["sim"]), 3),
                    })
            return results

    except Exception as exc:
        logger.warning(
            "Recherche titres similaires echouee: %s",
            exc,
            extra={"job_id": job_id[:8]},
        )
        return []


# ─── Nouveau prompt SEO pour les 21 langues en 1 appel ──────────────────────

SEO_ALL_LANGS_SYSTEM = (
    "Tu es un expert SEO senior specialise dans l'optimisation de contenus video "
    "multilingues. Tu generes des metadonnees SEO en UN SEUL appel pour 21 langues "
    "differentes.\n\n"
    "Regles strictes :\n"
    "1. **Chaque titre DOIT etre une question** se terminant par `?` — c'est la regle la plus importante.\n"
    "2. Chaque titre et description dans la langue native du public cible.\n"
    "3. Titre : 40-55 caracteres. Mot-cle principal a gauche.\n"
    "4. Description : 120-155 caracteres. Structure : Probleme -> Solution -> CTA.\n"
    "5. H1 : Variante du titre (50-70 chars).\n"
    "6. Keywords : 5-10 mots-cles longue traine dans la langue cible.\n"
    "7. Pas de tirets dans les titres (`--`, `—`, `-`) — utiliser `:` avec espaces si necessaire.\n"
    "8. Amorces variees : Comment, Pourquoi, Quel, Que, Combien, Est-ce que, Arrêtez de..., Faut-il...\n"
    "9. Les titres doivent etre UNIQUES et adaptes a chaque marche linguistique.\n"
    "10. Si la duree < 60s : titres adaptes aux Shorts/Reels (30-45 chars, punchy).\n\n"
    "Format de sortie : UNIQUEMENT un JSON valide, sans commentaire autour.\n"
    "Le JSON doit avoir une clef par code langue (fr, en, es, de, ...).\n"
    "Chaque valeur est un objet avec title, description, h1, keywords."
)

SEO_ALL_LANGS_USER = """Genere des metadonnees SEO optimisees pour les 21 langues ci-dessous.

=== TITRE BRUT (yt-dlp) ===
{raw_title}

=== CATEGORIE DETECTEE ===
{category}

=== DUREE (secondes) ===
{duration_s}

=== RESUME VIDEO ===
{summary}

=== CONTENU INSIGHTS ===
{content_insights}

=== LANGUES A GENERER ===
{langs_list}

---
Consignes (respecter l'ordre de priorite) :
1. Chaque titre DOIT etre une question finissant par `?`
2. Le titre et la description doivent etre dans la langue native du public cible
3. Les titres doivent etre UNIQUES entre eux
4. Si la duree < 60s : titres adaptes aux Shorts/Reels
5. Si categorie "tutorial" : titre commencant par "Comment ", "Tutoriel " ou "Apprendre a "
6. Mot-cle principal dans les 50 premiers caracteres de chaque titre
7. Description : 120-155 caracteres
8. Interdire les tirets (`--`, `—`, `-`) dans les titres -- utiliser ` : ` si necessaire
9. Adapte les keywords a chaque marche linguistique (expressions locales)

Reponds UNIQUEMENT avec ce JSON (21 langues) :
{{
  "fr": {{ "title": "... ?", "description": "...", "h1": "...", "keywords": [...] }},
  "en": {{ "title": "... ?", "description": "...", "h1": "...", "keywords": [...] }},
  ...
}}"""

# Liste des 21 langues supportees
ALL_SEO_LANGS = [
    "fr", "en", "es", "de", "it", "pt", "nl", "pl",
    "ru", "zh", "ja", "ko", "ar", "hi", "tr", "vi",
    "he", "fa", "id", "uk", "th",
]

LANG_NAMES_FOR_PROMPT = {
    "fr": "Francais", "en": "English", "es": "Espanol", "de": "Deutsch",
    "it": "Italiano", "pt": "Portugues", "nl": "Nederlands", "pl": "Polski",
    "ru": "Russkiy", "zh": "Zhongwen", "ja": "Nihongo", "ko": "Hangugeo",
    "ar": "Al-arabiyya", "hi": "Hindi", "tr": "Turkce", "vi": "Tieng Viet",
    "he": "Ivrit", "fa": "Farsi", "id": "Bahasa Indonesia", "uk": "Ukrayinska",
    "th": "Phasa Thai",
}


async def generate_seo_all_langs(
    job_id: str,
    raw_title: str,
    category: str = "",
    duration_s: float = 0,
    summary: str = "",
    analysis_result: dict | None = None,
    source_lang: str = "",
    skip_langs: set[str] | None = None,
) -> dict:
    """
    Genere les metadonnees SEO pour les 21 langues en UN SEUL appel LLM.
    Retourne un dict multilingue pret a etre stocke dans seo_metadata JSONB.

    Exemple de retour :
    {
        "fr": {"title": "...", "description": "...", "h1": "...", "keywords": [...]},
        "en": {"title": "...", "description": "...", "h1": "...", "keywords": [...]},
        ...
    }
    """
    log_extra = {
        "job_id": job_id[:8] if len(job_id) > 8 else job_id,
    }
    logger.info("Generation SEO multilingue (21 langues en 1 appel)", extra=log_extra)

    skip = skip_langs or set()
    langs_to_generate = [l for l in ALL_SEO_LANGS if l not in skip]

    # Preparer le contenu insights
    content_insights = {}
    if analysis_result:
        content_insights = analysis_result.get("content_insights", {}) or {}
    insights_str = json.dumps(content_insights, indent=2, ensure_ascii=False)[:800]

    # Lister les langues avec leurs noms
    langs_list_lines = []
    for lang in langs_to_generate:
        name = LANG_NAMES_FOR_PROMPT.get(lang, lang)
        langs_list_lines.append(f"  - {lang} ({name})")
    langs_list_str = "\n".join(langs_list_lines)

    user_prompt = SEO_ALL_LANGS_USER.format(
        raw_title=raw_title[:300],
        category=category or "non classifiee",
        duration_s=int(duration_s),
        summary=summary[:500] if summary else "non disponible",
        content_insights=insights_str or "non disponible",
        langs_list=langs_list_str,
    )

    try:
        start_ts = datetime.now(timezone.utc)
        raw_response = await call_openrouter(
            messages=[
                {"role": "system", "content": SEO_ALL_LANGS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            model=PRIMARY_MODEL,
            temperature=0.3,
            max_tokens=4096,
            user_id=f"seo_all_{job_id}",
            cache_key=f"seo_all|{job_id[:16]}",
        )
        result_text = (
            raw_response[0] if isinstance(raw_response, tuple) else raw_response
        )

        if not result_text:
            logger.warning("SEO multilingue: reponse vide", extra=log_extra)
            return {}

        cleaned = result_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            seo_all = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            logger.warning(
                "SEO multilingue: JSON invalide",
                extra={"error": str(exc)[:100], **log_extra},
            )
            return {}

        # Valider et nettoyer chaque entree de langue
        validated: dict[str, dict] = {}
        for lang_code in langs_to_generate:
            entry = seo_all.get(lang_code, {})
            if not isinstance(entry, dict):
                continue

            title = (entry.get("title") or "").strip()
            description = (entry.get("description") or "").strip()
            h1 = (entry.get("h1") or "").strip()
            keywords = entry.get("keywords", [])

            if not title:
                continue

            # Validation taille
            if len(title) > TITLE_MAX_CHARS:
                title = title[:TITLE_MAX_CHARS].rsplit(" ", 1)[0] if " " in title[:TITLE_MAX_CHARS] else title[:TITLE_MAX_CHARS]
            if len(description) > DESC_MAX_CHARS:
                description = description[:DESC_MAX_CHARS].rsplit(" ", 1)[0] if " " in description[:DESC_MAX_CHARS] else description[:DESC_MAX_CHARS]

            validated[lang_code] = {
                "title": title,
                "description": description[:DESC_MAX_CHARS],
                "h1": (h1 or title)[:H1_MAX_CHARS],
                "keywords": (keywords if isinstance(keywords, list) else [])[:KEYWORDS_MAX],
                "generated_at": start_ts.isoformat(),
                "char_count_title": len(title),
                "char_count_description": len(description),
            }

        logger.info(
            "SEO multilingue genere: %d langues valides",
            len(validated),
            extra=log_extra,
        )
        return validated

    except Exception as exc:
        logger.error(
            "SEO multilingue: echec",
            extra={"error": str(exc), **log_extra},
        )
        return {}


# ─── Anciens prompts SEO (gardes pour retrocompatibilite) ────────────────────

SEO_PROMPT_SHORT = (
    "Tu es un expert SEO senior specialise dans l'optimisation de contenus video "
    "formats courts (Shorts/Reels). Tu generes des metadonnees SEO percutantes "
    "et adaptees au format court.\n\n"
    "Regles strictes SEO Short :\n"
    "1. **Titre** : 30-50 caracteres. Accroche hyper-percutante, question ou chiffre.\n"
    "2. **Titre DOIT etre une question** : terminer obligatoirement par `?`.\n"
    "3. **Meta description** : 80-120 caracteres. Ultra-concise, benefice immediat.\n"
    "4. **H1** : Variante du titre (30-50 chars).\n"
    "5. **Keywords** : 3-5 mots-cles, focus sur le viral/trending.\n"
    "6. **Tone** : Punchy, viral, accrocheur — comme un titre de Reel qui \"scrolle stop\".\n"
    "7. **Pas de tirets** : utiliser `:` avec espaces si necessaire.\n\n"
    "Format de sortie : UNIQUEMENT un JSON valide, sans commentaire autour."
)

SEO_PROMPT_STANDARD = (
    "Tu es un expert SEO senior specialise dans l'optimisation de contenus video "
    "multilingues. Tu generes des metadonnees SEO parfaitement adaptees a la "
    "langue et au marche cible.\n\n"
    "Regles strictes SEO :\n"
    "1. **Titre** : 40-55 caracteres (max 55). Mot-cle principal a gauche. Unique. Pas de keyword stuffing.\n"
    "2. **Titre DOIT etre une question** : terminer obligatoirement par `?`. Priorite maximale.\n"
    "3. **Interdiction des tirets** : ne jamais utiliser `--`, `—`, `-`. Utiliser `:` avec espace avant et apres si necessaire.\n"
    "4. **Meta description** : 120-155 caracteres. Structure : Probleme -> Solution -> CTA.\n"
    "5. **H1** : Variante du titre (50-70 chars), formulation differente.\n"
    "6. **Keywords** : 5-10 mots-cles longue traine.\n"
    "7. **Amorces variees** : Comment, Pourquoi, Quel, Que, Combien, Est-ce que, Arrêtez de..., Faut-il...\n"
    "8. **Chiffre devant si applicable** : ex. \"3 facons de...\"\n"
    "9. **Tutorial** : si categorie tutorial, commencer par Comment, Tutoriel, Apprendre a.\n\n"
    "Proscrire les titres generiques sans question. Exemple :\n"
    "  ❌ \"n8n + Claude Code : Automatisez vos workflows\"\n"
    "  ✅ \"Comment automatiser vos workflows en 1 clic avec n8n et Claude Code ?\"\n\n"
    "Format de sortie : UNIQUEMENT un JSON valide, sans commentaire autour."
)

SEO_PROMPT_LONGFORM = (
    "Tu es un expert SEO senior specialise dans l'optimisation de contenus video "
    "longs-formats (analyses approfondies, tutoriels detailles, conferences). "
    "Tu generes des metadonnees SEO riches et structurées.\n\n"
    "Regles strictes SEO Long-Form :\n"
    "1. **Titre** : 50-60 caracteres. Descriptif, informatif, question ou promesse de valeur.\n"
    "2. **Titre DOIT etre une question** : terminer obligatoirement par `?`.\n"
    "3. **Interdiction des tirets** : utiliser `:` avec espaces si necessaire.\n"
    "4. **Meta description** : 140-160 caracteres. Structure : Contexte -> Analyse approfondie -> CTA.\n"
    "5. **H1** : Variante du titre (60-75 chars), formulation plus riche.\n"
    "6. **Keywords** : 8-12 mots-cles longue traine, couvrant les sous-themes.\n"
    "7. **Amorces variees** : Comment, Pourquoi, Analyse de, Guide complet, Tout savoir sur, Le guide ultime de...\n"
    "8. **Tonalite** : Expert, autoritaire, pedagogique — comme une formation ou une analyse.\n"
    "9. **Suggestion structure** : mentionner subtilement que le contenu est structuré (parties, chapitres).\n\n"
    "Format de sortie : UNIQUEMENT un JSON valide, sans commentaire autour."
)


def _get_seo_prompt(seo_prompt_type: str = "standard") -> str:
    """Retourne le prompt systeme SEO approprie selon le type."""
    prompts = {
        "short": SEO_PROMPT_SHORT,
        "standard": SEO_PROMPT_STANDARD,
        "longform": SEO_PROMPT_LONGFORM,
    }
    return prompts.get(seo_prompt_type, SEO_PROMPT_STANDARD)


SEO_USER_TEMPLATE = """Genere des metadonnees SEO optimisees pour cette video traduite.

=== LANGUE CIBLE ===
{target_lang}

=== TITRE BRUT (yt-dlp) ===
{raw_title}

=== CATEGORIE DETECTEE ===
{category}

=== DUREE (secondes) ===
{duration_s}

=== RESUME VIDEO ===
{summary}

=== SUGGESTIONS SEO EXISTANTES ===
{suggestions}

=== CONTENU INSIGHTS ===
{content_insights}

=== TITRES A EVITER (meme categorie) ===
{similar_titles}

---
Consignes (respecter l'ordre de priorite) :
1. **Le titre DOIT obligatoirement etre une question** finissant par `?` -- c'est la regle la plus importante, priorite maximale.
2. Le titre et la description doivent etre en langue {target_lang_name}
3. Le titre doit etre UNIQUE (pas de doublon avec d'autres contenus) -- eviter les titres listes ci-dessus
4. Si la duree < 60s : titre adapte aux Shorts/Reels
5. Si categorie "tutorial" : titre commencant par "Comment ", "Tutoriel " ou "Apprendre a "
6. Mot-cle principal dans les 50 premiers caracteres du titre
7. Description : 120-155 caracteres, phrase d'accroche + benefice + CTA
8. H1 : variante du titre (pas identique), formulation naturelle
9. Interdire les tirets (`--`, `—`, `-`) dans le titre -- utiliser ` : ` (espace-:-espace) si necessaire

Amorces recommandees pour les questions : Comment, Pourquoi, Quel, Que, Combien, Est-ce que, Arrêtez de..., Faut-il..., Peut-on...

Exemple de titre valide : "Comment automatiser vos workflows en 1 clic avec n8n et Claude Code ?"

Reponds UNIQUEMENT avec ce JSON :
{{
  "title": "Titre SEO optimise (40-60 chars, DOIT finir par ?)",
  "description": "Meta description optimisee (120-155 chars)",
  "h1": "H1 pour la page (50-70 chars)",
  "keywords": ["keyword1", "keyword2", ...]
}}"""


def _validate_seo_field(value: str, field_name: str, min_chars: int, max_chars: int, lang: str = "") -> str:
    """Tronque un champ SEO si trop long, paddingu automatique si trop court."""
    if not value:
        logger.warning("Champ SEO vide: %s", field_name)
        return value
    if len(value) > max_chars:
        logger.info(
            "Champ SEO %s tronque: %d -> %d chars",
            field_name,
            len(value),
            max_chars,
        )
        value = (
            value[:max_chars].rsplit(" ", 1)[0]
            if " " in value[:max_chars]
            else value[:max_chars]
        )
    # Ajouter ? si titre francais sans point d'interrogation
    if field_name == "title" and lang == "fr" and not value.rstrip().endswith("?"):
        value = value.rstrip() + " ?"
    elif len(value) < min_chars:
        logger.info(
            "Champ SEO %s padde: %d -> %d chars",
            field_name,
            len(value),
            min_chars,
        )
        # Paddingu automatique avec le dernier mot du champ
        last_word = value.rsplit(" ", 1)[-1] if " " in value else value
        needed = min_chars - len(value)
        padding = " " + " ".join([last_word] * (needed // len(last_word) + 1))
        value = (value + padding)[:max_chars]
    return value


def _validate_title_is_question(title: str) -> None:
    """Avertit si le titre SEO ne se termine pas par ?."""
    if title and not title.rstrip().endswith("?"):
        logger.warning(
            "Titre SEO ne se termine pas par ? : «%s» (%d chars)",
            title[:50], len(title),
        )


async def _save_seo_slug(job_id: str, slug: str) -> bool:
    """Sauvegarde le seo_slug dans jobs.seo_slug."""
    if not slug:
        return False
    try:
        from core.db import direct_connect as _direct
        from uuid import UUID

        async with _direct() as conn:
            await conn.execute(
                "UPDATE jobs SET seo_slug=$1, updated_at=now() WHERE id=$2",
                slug,
                UUID(job_id),
            )
            logger.info(
                "Slug sauvegarde: %s",
                slug,
                extra={"job_id": job_id[:8]},
            )
            return True
    except Exception as exc:
        logger.warning(
            "Sauvegarde slug echouee: %s",
            exc,
            extra={"job_id": job_id[:8]},
        )
        return False


def _get_language_name(lang_code: str) -> str:
    """Convertit un code langue court en nom lisible."""
    names = {
        "fr": "francais",
        "en": "anglais",
        "es": "espagnol",
        "de": "allemand",
        "it": "italien",
        "pt": "portugais",
        "nl": "neerlandais",
        "ja": "japonais",
        "ko": "coreen",
        "zh": "chinois",
        "ru": "russe",
        "ar": "arabe",
        "hi": "hindi",
        "th": "thai",
        "vi": "vietnamien",
        "tr": "turc",
        "pl": "polonais",
        "sv": "suedois",
        "da": "danois",
        "no": "norvegien",
        "fi": "finnois",
    }
    return names.get(lang_code[:2], lang_code)


async def save_seo_metadata_multilingual(
    job_id: str,
    seo_all: dict,
) -> bool:
    """
    Sauvegarde les metadonnees SEO pour TOUTES les langues d'un coup.
    Merge avec l'existant pour ne pas ecraser les langues deja presentes.
    Genere et sauvegarde le seo_slug a partir de la langue source (fr ou en).
    """
    if not seo_all:
        return False

    try:
        from core.db import direct_connect as _direct
        from uuid import UUID
        import json as _json

        async with _direct() as conn:
            row = await conn.fetchrow(
                "SELECT seo_metadata, created_at, seo_slug FROM jobs WHERE id=$1",
                UUID(job_id),
            )
            if not row:
                logger.warning(
                    "Job introuvable pour sauvegarde SEO multilingue",
                    extra={"job_id": job_id[:8]},
                )
                return False

            existing = {}
            if row["seo_metadata"]:
                val = row["seo_metadata"]
                if isinstance(val, str):
                    try:
                        existing = _json.loads(val)
                    except Exception:
                        existing = {}
                elif isinstance(val, dict):
                    existing = val

            # Merge (ne pas ecraser les langues deja presentes)
            merged = {**existing}
            for lang, seo_entry in seo_all.items():
                if lang not in existing or not existing[lang].get("title"):
                    merged[lang] = seo_entry

            await conn.execute(
                "UPDATE jobs SET seo_metadata=$1, updated_at=now() WHERE id=$2",
                _json.dumps(merged),
                UUID(job_id),
            )

            # Generer le slug si pas deja present
            if not row["seo_slug"]:
                # Prendre le titre français ou anglais
                for lang_key in ["fr", "en"]:
                    title = seo_all.get(lang_key, {}).get("title", "")
                    if title:
                        job_created_at = row["created_at"]
                        if isinstance(job_created_at, datetime):
                            job_created_at_str = job_created_at.isoformat()
                        else:
                            job_created_at_str = str(job_created_at) if job_created_at else None

                        slug = _title_to_slug(title, lang_key, job_created_at_str)
                        if slug:
                            await _save_seo_slug(job_id, slug)
                        break

            logger.info(
                "SEO multilingue sauvegarde: %d langues",
                len(seo_all),
                extra={"job_id": job_id[:8]},
            )
            return True

    except Exception as exc:
        logger.error(
            "Sauvegarde SEO multilingue echouee: %s",
            exc,
            extra={"job_id": job_id[:8]},
        )
        return False


# ─── Anciennes fonctions (gardees pour retrocompatibilite) ────────────────────


async def generate_seo_metadata(
    job_id: str,
    target_lang: str,
    raw_title: str,
    category: str = "",
    duration_s: float = 0,
    summary: str = "",
    analysis_result: dict | None = None,
    source_lang: str = "",
) -> dict:
    """
    Genere les metadonnees SEO pour UNE langue donnee via DeepSeek V3.1.
    Ancienne version — un appel par langue.
    Conservee pour retrocompatibilite et fallback.
    """
    log_extra = {
        "job_id": job_id[:8] if len(job_id) > 8 else job_id,
        "lang": target_lang,
    }
    logger.info("Generation SEO pour langue=%s (legacy)", target_lang, extra=log_extra)

    fusion_seo = {}
    content_insights = {}
    if analysis_result:
        fusion_seo = analysis_result.get("seo", {}) or {}
        content_insights = analysis_result.get("content_insights", {}) or {}

    suggestions_str = json.dumps(fusion_seo, indent=2, ensure_ascii=False)
    insights_str = json.dumps(content_insights, indent=2, ensure_ascii=False)

    # ── Anti-doublon : chercher des titres similaires dans la meme categorie ──
    similar_titles_str = ""
    try:
        similar_titles = await _find_similar_titles(
            title=raw_title,
            category=category,
            lang=target_lang,
            job_id=job_id,
            threshold=0.4,
            limit=5,
        )
        if similar_titles:
            similar_lines = []
            for st in similar_titles:
                similar_lines.append(
                    f"  - \"{st['title']}\" (similarite: {st['similarity']}, job: {st['job_id'][:8]})"
                )
            similar_titles_str = "\n".join(similar_lines)
            logger.info(
                "%d titre(s) similaire(s) detecte(s) pour anti-doublon",
                len(similar_titles),
                extra=log_extra,
            )
    except Exception as exc:
        logger.warning(
            "Anti-doublon: recherche titres similaires echouee: %s",
            exc,
            extra=log_extra,
        )

    user_prompt = SEO_USER_TEMPLATE.format(
        target_lang=target_lang,
        target_lang_name=_get_language_name(target_lang),
        raw_title=raw_title[:300],
        category=category or "non classifiee",
        duration_s=int(duration_s),
        summary=summary[:500] if summary else "non disponible",
        suggestions=suggestions_str[:500],
        content_insights=insights_str[:500],
        similar_titles=similar_titles_str or "Aucun titre similaire detecte",
    )

    try:
        # Choisir le prompt SEO selon le palier de durée
        seo_system_prompt = _get_seo_prompt(
            "short" if duration_s < 120 else ("longform" if duration_s >= 900 else "standard")
        )
        raw_response = await call_openrouter(
            messages=[
                {"role": "system", "content": seo_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=PRIMARY_MODEL,
            temperature=0.3,
            max_tokens=1024,
            user_id=f"seo_{job_id}",
            cache_key=f"seo|{job_id[:16]}|{target_lang}",
        )
        result_text = (
            raw_response[0] if isinstance(raw_response, tuple) else raw_response
        )

        if not result_text:
            logger.warning("SEO: reponse vide -- fallback", extra=log_extra)
            return {}

        cleaned = result_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            seo_data = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            logger.warning(
                "SEO: reponse JSON invalide -- fallback",
                extra={"error": str(exc), **log_extra},
            )
            return {}

        title = seo_data.get("title", "").strip()
        description = seo_data.get("description", "").strip()
        h1 = seo_data.get("h1", "").strip()
        keywords = seo_data.get("keywords", [])

        if not title:
            title = fusion_seo.get(
                "suggested_title",
                raw_title[:60] if raw_title else f"Video traduite ({target_lang})",
            )
        if not description:
            description = fusion_seo.get(
                "suggested_description",
                summary[:155] if summary else "",
            )
            if not description:
                lang_name = _get_language_name(target_lang)
                description = (
                    f"{raw_title[:50]} — Regardez cette video traduite en "
                    f"{lang_name} avec des sous-titres de qualite. "
                    f"Decouvrez le contenu original adapte pour un public {lang_name}."
                )[:155]
        if not h1:
            h1 = title[:H1_MAX_CHARS]
        if not keywords:
            keywords = fusion_seo.get("seo_keywords", [])[:KEYWORDS_MAX]

        _validate_title_is_question(title)
        title = _validate_seo_field(title, "title", TITLE_MIN_CHARS, TITLE_MAX_CHARS, lang=target_lang)
        description = _validate_seo_field(
            description, "description", DESC_MIN_CHARS, DESC_MAX_CHARS
        )
        h1 = _validate_seo_field(h1, "h1", 30, H1_MAX_CHARS)
        keywords = keywords[:KEYWORDS_MAX]

        result = {
            "title": title,
            "description": description,
            "h1": h1,
            "keywords": keywords,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "char_count_title": len(title),
            "char_count_description": len(description),
        }

        logger.info(
            "SEO genere: title=%d chars desc=%d chars kw=%d -- %s",
            len(title),
            len(description),
            len(keywords),
            title[:50],
            extra=log_extra,
        )
        return result

    except Exception as exc:
        logger.error(
            "SEO: echec generation",
            extra={"error": str(exc), **log_extra},
        )
        return {}


async def save_seo_metadata(
    job_id: str,
    lang: str,
    seo_data: dict,
) -> bool:
    """
    Sauvegarde les metadonnees SEO dans jobs.seo_metadata (JSONB).
    Merge avec l'existant pour ne pas ecraser les autres langues.
    Ancienne version — une langue a la fois.
    """
    if not seo_data:
        return False

    try:
        from core.db import direct_connect as _direct
        from uuid import UUID
        import json as _json

        async with _direct() as conn:
            row = await conn.fetchrow(
                "SELECT seo_metadata, created_at FROM jobs WHERE id=$1",
                UUID(job_id),
            )
            if not row:
                logger.warning(
                    "Job introuvable pour sauvegarde SEO",
                    extra={"job_id": job_id[:8]},
                )
                return False

            existing = {}
            if row["seo_metadata"]:
                val = row["seo_metadata"]
                if isinstance(val, str):
                    try:
                        existing = _json.loads(val)
                    except Exception:
                        existing = {}
                elif isinstance(val, dict):
                    existing = val

            existing[lang] = seo_data

            await conn.execute(
                "UPDATE jobs SET seo_metadata=$1, updated_at=now() WHERE id=$2",
                _json.dumps(existing),
                UUID(job_id),
            )

            # Generer le seo_slug si c'est la premiere langue sauvegardee
            existing_slug_row = await conn.fetchrow(
                "SELECT seo_slug FROM jobs WHERE id=$1",
                UUID(job_id),
            )
            if existing_slug_row and existing_slug_row["seo_slug"]:
                pass  # Slug deja existant → ne pas ecraser
            else:
                title = seo_data.get("title", "")
                if title:
                    job_created_at = row["created_at"]
                    if isinstance(job_created_at, datetime):
                        job_created_at_str = job_created_at.isoformat()
                    else:
                        job_created_at_str = str(job_created_at) if job_created_at else None

                    slug = _title_to_slug(title, lang, job_created_at_str)
                    if slug:
                        await _save_seo_slug(job_id, slug)

            return True

    except Exception as exc:
        logger.error(
            "Sauvegarde SEO echouee: %s",
            exc,
            extra={"job_id": job_id[:8]},
        )
        return False