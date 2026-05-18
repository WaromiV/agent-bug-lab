from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.settings import SettingsPatch, SettingsRead
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def get_settings_endpoint(db: DbSession) -> SettingsRead:
    return SettingsRead.model_validate(settings_service.get_or_init(db))


@router.patch("", response_model=SettingsRead)
def patch_settings(payload: SettingsPatch, db: DbSession) -> SettingsRead:
    return SettingsRead.model_validate(settings_service.patch(db, payload))
