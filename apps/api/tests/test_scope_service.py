"""Scope ops are the project's headline feature: agents may create and rename
scopes but never delete them, and id references must resolve deterministically."""
from __future__ import annotations

import pytest

from app.db.models import Scope
from app.services import scope_service
from app.services.scope_service import ScopeOpsError


def _names(db, project_id):
    return {s.name for s in scope_service.list_for_project(db, project_id)}


# ── create ──────────────────────────────────────────────────────────────────
def test_create_adds_scope_and_maps_requested_id(db, project):
    id_map = scope_service.apply_scope_ops(
        db, project.id, {"create": [{"id": "scope_race", "name": "Race conditions"}]}
    )
    assert "Race conditions" in _names(db, project.id)
    # The agent-supplied id is mapped to the real (project-qualified) id.
    real = id_map["scope_race"]
    assert real.endswith(f"__{project.id}")
    assert db.get(Scope, real) is not None


def test_create_coalesces_into_existing_scope_by_name_case_insensitive(db, project):
    scope_service.create(
        db,
        project_id=project.id,
        payload=scope_service.ScopeCreate(name="Memory Safety"),
        explicit_id="scope_mem",
    )
    id_map = scope_service.apply_scope_ops(
        db, project.id, {"create": [{"id": "tmp", "name": "memory safety"}]}
    )
    # No duplicate row created; the temp id points at the existing scope.
    assert len([s for s in scope_service.list_for_project(db, project.id)]) == 1
    assert id_map["tmp"] == "scope_mem"


def test_create_requires_nonempty_name(db, project):
    with pytest.raises(ScopeOpsError, match="name is required"):
        scope_service.apply_scope_ops(db, project.id, {"create": [{"id": "x", "name": "  "}]})


# ── rename ──────────────────────────────────────────────────────────────────
def test_rename_changes_name(db, project):
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="old"), explicit_id="scope_r",
    )
    scope_service.apply_scope_ops(
        db, project.id, {"rename": [{"id": "scope_r", "name": "new"}]}
    )
    assert _names(db, project.id) == {"new"}


def test_rename_unknown_scope_raises(db, project):
    with pytest.raises(ScopeOpsError, match="not found"):
        scope_service.apply_scope_ops(
            db, project.id, {"rename": [{"id": "nope", "name": "x"}]}
        )


def test_rename_to_empty_name_raises(db, project):
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="old"), explicit_id="scope_r",
    )
    with pytest.raises(ScopeOpsError, match="is empty"):
        scope_service.apply_scope_ops(
            db, project.id, {"rename": [{"id": "scope_r", "name": ""}]}
        )


# ── delete is a no-op, never an error ─────────────────────────────────────────
def test_delete_entries_are_silently_ignored(db, project):
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="keep"), explicit_id="scope_k",
    )
    # delete must neither raise nor remove anything.
    scope_service.apply_scope_ops(db, project.id, {"delete": ["scope_k"]})
    assert db.get(Scope, "scope_k") is not None


# ── shape validation ──────────────────────────────────────────────────────────
def test_none_scope_ops_returns_empty_map(db, project):
    assert scope_service.apply_scope_ops(db, project.id, None) == {}


def test_non_dict_scope_ops_raises(db, project):
    with pytest.raises(ScopeOpsError, match="must be an object"):
        scope_service.apply_scope_ops(db, project.id, ["create"])


# ── resolve_scope_id ──────────────────────────────────────────────────────────
def test_resolve_prefers_id_map(db, project):
    assert scope_service.resolve_scope_id(db, project.id, "tmp", {"tmp": "scope_real"}) == "scope_real"


def test_resolve_direct_hit(db, project):
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="s"), explicit_id="scope_direct",
    )
    assert scope_service.resolve_scope_id(db, project.id, "scope_direct", {}) == "scope_direct"


def test_resolve_tolerates_unqualified_semantic_prefix(db, project):
    qualified = f"scope_xss__{project.id}"
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="xss"), explicit_id=qualified,
    )
    # Agent referenced the bare prefix; resolver appends __<project_id>.
    assert scope_service.resolve_scope_id(db, project.id, "scope_xss", {}) == qualified


def test_resolve_unknown_raises(db, project):
    with pytest.raises(ScopeOpsError, match="unresolved scope id"):
        scope_service.resolve_scope_id(db, project.id, "ghost", {})
