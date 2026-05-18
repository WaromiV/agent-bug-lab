from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal


def db_session() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(db_session)]


_pool: ArqRedis | None = None


async def get_arq_pool() -> AsyncIterator[ArqRedis]:
    global _pool
    if _pool is None:
        cfg = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(cfg.redis_url))
    yield _pool


ArqPool = Annotated[ArqRedis, Depends(get_arq_pool)]
