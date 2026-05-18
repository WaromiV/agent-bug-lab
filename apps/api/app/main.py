from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import bugs, harnesses, logs, projects, reviews, runs, scopes
from app.api.routes import settings as settings_route
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.services import settings_service

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    with SessionLocal() as s:
        settings_service.get_or_init(s)
        s.commit()
    log.info("api.started")
    yield
    log.info("api.stopped")


app = FastAPI(title="agent-bug-lab", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for r in (
    projects.router,
    runs.router,
    bugs.router,
    reviews.router,
    settings_route.router,
    harnesses.router,
    logs.router,
    scopes.router,
):
    app.include_router(r, prefix="/api")
