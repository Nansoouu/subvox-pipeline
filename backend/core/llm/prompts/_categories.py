"""
_categories.py — Catégories vidéo et voix par catégorie (DeepSeek V3)
"""

CATEGORIES = [
    "tutorial",      # Tutoriel, guide pas à pas, how-to
    "tech",          # Tech, code, IA, hardware, logiciel
    "news",          # Actualités, politique, société
    "entertainment", # Divertissement, humour, vlog, gaming
    "education",     # Éducation, cours, science, histoire
    "music",         # Musique, concert, clip
    "sports",        # Sport, fitness, aventure
    "business",      # Business, finance, entrepreneuriat
    "lifestyle",     # Lifestyle, cuisine, voyage, bien-être
    "other",         # Autre (fallback)
]

# ─── Voix par catégorie (instructions ajoutées au prompt) ──────
CATEGORY_VOICES: dict[str, str] = {
    "tutorial": (
        "Adopte un ton de guide pédagogique, patient et clair. "
        "Explique comme si tu montrais la voie à un ami débutant."
    ),
    "tech": (
        "Adopte un ton d'analyste tech passionné, précis mais accessible. "
        "Montre l'impact concret de chaque innovation."
    ),
    "news": (
        "Adopte un ton de journaliste rigoureux et neutre. "
        "Rapporte les faits avec précision sans parti pris."
    ),
    "entertainment": (
        "Adopte un ton de critique enthousiaste mais honnête. "
        "Donne envie de regarder la vidéo avec du punch et du rythme."
    ),
    "education": (
        "Adopte un ton de professeur passionné qui rend chaque concept "
        "fascinant et compréhensible par tous."
    ),
    "music": (
        "Adopte un ton de critique musical, sensible aux émotions "
        "et aux ambiances sonores. Décris ce qu'on ressent à l'écoute."
    ),
    "sports": (
        "Adopte un ton de commentateur sportif dynamique et immersif. "
        "Fais vivre l'action comme si on y était."
    ),
    "business": (
        "Adopte un ton d'analyste financier pragmatique. "
        "Va droit à l'essentiel : opportunités, risques, chiffres clés."
    ),
    "lifestyle": (
        "Adopte un ton chaleureux inspirant, comme un magazine lifestyle. "
        "Donne envie d'adopter ces astices au quotidien."
    ),
    "other": (
        "Adopte un ton naturel et fluide, comme un article de blog "
        "bien écrit. Sois clair, direct et captivant."
    ),
}