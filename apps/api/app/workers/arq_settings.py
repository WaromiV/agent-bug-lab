from __future__ import annotations

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.cleaner_worker import run_cleaner
from app.workers.debate_worker import run_debate
from app.workers.prepare_worker import run_prepare
from app.workers.searcher_worker import run_searcher


async def startup(ctx: dict) -> None:
    configure_logging()


class WorkerSettings:
    functions = [run_searcher, run_cleaner, run_prepare, run_debate]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = get_settings().run_timeout_seconds + 60
