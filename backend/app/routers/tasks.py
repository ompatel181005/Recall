"""Which provider/model each AI task can run on right now.

Read straight out of config.yaml so the frontend never hard-codes a model name
— adding a comparison target is a config edit, not a code change.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import ProviderOption
from ..services.providers.registry import options_for_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task}/providers", response_model=list[ProviderOption])
def task_providers(task: str) -> list[dict]:
    if task not in settings.tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task}' is not defined in config.yaml under tasks:",
        )
    return options_for_task(task)
