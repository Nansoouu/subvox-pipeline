"""
api/jobs/__init__.py — Router jobs pour Pipeline.

Contient uniquement les routes techniques (status, feed, burn, subtitles).
Ne contient PAS submit (économie) ni lifecycle (économie).
"""

from fastapi import APIRouter

from . import _models
from . import public
from . import status
from . import subtitles
from . import check_url

router = APIRouter()
router.include_router(public.router)
router.include_router(status.router)
router.include_router(subtitles.router)
router.include_router(check_url.router)

# Classes Pydantic
JobStatusResponse = _models.JobStatusResponse
STATUS_LABEL = _models.STATUS_LABEL
STATUS_PROGRESS = _models.STATUS_PROGRESS
