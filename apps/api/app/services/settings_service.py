from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Setting
from app.schemas.settings import SettingsPatch

GLOBAL_ID = "global"


def get_or_init(db: Session) -> Setting:
    s = db.get(Setting, GLOBAL_ID)
    if s is None:
        cfg = get_settings()
        s = Setting(
            id=GLOBAL_ID,
            selected_harness=cfg.default_harness,
            selected_model=cfg.default_model,
            selected_effort="max",
            use_resume_when_available=True,
        )
        db.add(s)
        db.flush()
    return s


def patch(db: Session, patch_in: SettingsPatch) -> Setting:
    s = get_or_init(db)
    data = patch_in.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(s, k, v)
    db.flush()
    return s
