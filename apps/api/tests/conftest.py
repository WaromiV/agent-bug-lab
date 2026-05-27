"""Shared fixtures.

The production DB is Postgres (JSONB columns, sequence-backed ids). For unit
tests we run against an in-memory SQLite engine instead:

  * JSONB is compiled down to SQLite's JSON storage class.
  * `app.core.ids.next_id` (a Postgres `nextval` call) is replaced with a
    per-kind in-process counter that yields the same `<prefix>_000001` shape.
    Both modules that import the symbol by name are patched.

This keeps the tests hermetic (no Postgres, no Redis, no network) while
exercising the real service code paths.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@pytest.fixture
def db(monkeypatch, tmp_path):
    """An isolated in-memory SQLite session with the full schema created."""
    from app.core import ids

    # data_dir is used by write_json side-effects in the services under test.
    from app.core.config import get_settings
    from app.db.models import Base

    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)

    counters: dict[str, int] = {}

    def fake_next_id(session, kind: str) -> str:  # noqa: ANN001
        counters[kind] = counters.get(kind, 0) + 1
        return f"{ids._PREFIX[kind]}_{counters[kind]:06d}"

    # The services import next_id by name, so patch each call site.
    monkeypatch.setattr("app.core.ids.next_id", fake_next_id)
    monkeypatch.setattr("app.services.scope_service.next_id", fake_next_id)
    monkeypatch.setattr("app.services.bug_ingest.next_id", fake_next_id)

    with Session(engine, future=True) as session:
        yield session

    get_settings.cache_clear()


@pytest.fixture
def project(db):
    """A persisted project row to hang scopes/bugs off of."""
    from app.db.models import Project

    p = Project(
        id="project_000001",
        name="demo",
        bug_bounty_url="https://example.invalid/bounty",
        repo_path="/tmp/repo",
    )
    db.add(p)
    db.flush()
    return p
