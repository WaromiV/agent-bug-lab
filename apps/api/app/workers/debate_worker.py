from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services import debate_service

log = get_logger(__name__)


async def run_debate(ctx: dict[str, Any], debate_id: str) -> None:  # noqa: ARG001
    await debate_service.drive_debate(debate_id)
