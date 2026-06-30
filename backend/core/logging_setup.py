"""
core/logging_setup.py — Logging structuré centralisé — Subvox

Fournit un logger structuré (format JSON) avec contexte automatique
(job_id, request_id, user_id, étape du pipeline).
Remplace tous les print() du projet par un vrai système de logs.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """Formatteur JSON structuré avec champs standardisés."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Contexte supplémentaire (job_id, request_id, etc.)
        if hasattr(record, "job_id") and record.job_id:
            log_entry["job_id"] = record.job_id
        if hasattr(record, "request_id") and record.request_id:
            log_entry["request_id"] = record.request_id
        if hasattr(record, "user_id") and record.user_id:
            log_entry["user_id"] = record.user_id
        if hasattr(record, "duration_ms") and record.duration_ms is not None:
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "step") and record.step:
            log_entry["step"] = record.step

        # Exception traceback si présent
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None,
) -> None:
    """Configure le logging global de l'application.

    Args:
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR)
        json_format: Si True, format JSON structuré. Sinon, format lisible.
        log_file: Chemin optionnel vers un fichier de log.
    """
    root_logger = logging.getLogger()

    # Niveau
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Supprimer les handlers existants
    root_logger.handlers.clear()

    # Handler stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        stdout_handler.setFormatter(StructuredFormatter())
    else:
        stdout_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    stdout_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(stdout_handler)

    # Handler fichier optionnel
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        if json_format:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

    # Réduire le bruit des librairies tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger avec le nom du module.

    Usage:
        logger = get_logger(__name__)
        logger.info("Message", extra={"job_id": job_id})
    """
    return logging.getLogger(name)
