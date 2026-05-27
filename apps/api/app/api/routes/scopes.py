from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.db.models import Project, Scope
from app.schemas.scope import ScopeCreate, ScopePatch, ScopeRead
from app.services import scope_service


def _serialize(scope: Scope) -> ScopeRead:
    return ScopeRead.model_validate(scope)

router = APIRouter(tags=["scopes"])


@router.get("/projects/{project_id}/scopes", response_model=list[ScopeRead])
def list_project_scopes(project_id: str, db: DbSession) -> list[ScopeRead]:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    return [_serialize(s) for s in scope_service.list_for_project(db, project_id)]


@router.post("/projects/{project_id}/scopes", response_model=ScopeRead, status_code=201)
def create_scope(project_id: str, payload: ScopeCreate, db: DbSession) -> ScopeRead:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    return _serialize(scope_service.create(db, project_id=project_id, payload=payload))


@router.get("/scopes/{scope_id}", response_model=ScopeRead)
def get_scope(scope_id: str, db: DbSession) -> ScopeRead:
    s = scope_service.get(db, scope_id)
    if s is None:
        raise HTTPException(404, "scope not found")
    return _serialize(s)


@router.patch("/scopes/{scope_id}", response_model=ScopeRead)
def patch_scope(scope_id: str, payload: ScopePatch, db: DbSession) -> ScopeRead:
    s = scope_service.get(db, scope_id)
    if s is None:
        raise HTTPException(404, "scope not found")
    return _serialize(scope_service.patch(db, s, payload))


# Scopes are intentionally immutable in terms of existence: agents and
# humans may create and rename, but never delete. Scopes accumulate as
# audit-trail vocabulary.
