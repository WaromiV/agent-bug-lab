"""validate_and_ingest is the trust boundary between agent JSON and the DB.
It must reject malformed output, enforce the findings-count window, rewrite
agent-advisory bug ids, and bind every bug to a real project scope."""
from __future__ import annotations

import pytest

from app.db.models import AgentRun, Bug, Scope
from app.services import scope_service
from app.services.bug_ingest import SearcherOutputError, validate_and_ingest


def _run(db, project, tmp_path):
    data_dir = tmp_path / "run_000001"
    data_dir.mkdir(parents=True, exist_ok=True)  # lifecycle creates this before ingest
    run = AgentRun(
        id="run_000001",
        project_id=project.id,
        role="searcher_agent",
        harness="codex",
        model="gpt-x",
        status="running",
        objective="find bugs",
        data_dir=str(data_dir),
        raw_input={},
    )
    db.add(run)
    db.flush()
    return run


def _seed_scope(db, project, scope_id="scope_mem"):
    scope_service.create(
        db, project_id=project.id,
        payload=scope_service.ScopeCreate(name="memory safety"),
        explicit_id=scope_id,
    )
    return scope_id


def _bug(scope_id, **over):
    base = {
        "id": "bug_advisory_1",
        "severity": "high",
        "scope_id": scope_id,
        "description": "desc",
        "repro_path": "poc/x",
        "repro_usage": "run",
        "missing_for_full_chain": "nothing",
    }
    base.update(over)
    return base


# ── happy path ────────────────────────────────────────────────────────────--
def test_ingest_inserts_bug_and_rewrites_advisory_id(db, project, tmp_path):
    sid = _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    inserted = validate_and_ingest(
        db, run, {"status": "ok", "bugs": [_bug(sid)]}, min_findings=1, max_findings=5
    )
    assert len(inserted) == 1
    # Advisory id from the model is discarded in favor of a server id.
    assert inserted[0].id != "bug_advisory_1"
    assert inserted[0].id.startswith("bug_")
    assert inserted[0].owner_run_id == run.id
    assert db.get(Bug, inserted[0].id) is not None


def test_ingest_writes_validated_bugs_artifact(db, project, tmp_path):
    sid = _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    validate_and_ingest(
        db, run, {"status": "ok", "bugs": [_bug(sid)]}, min_findings=1, max_findings=5
    )
    artifact = tmp_path / "run_000001" / "validated_bugs.json"
    assert artifact.exists()


def test_ingest_resolves_newly_created_scope_in_same_response(db, project, tmp_path):
    run = _run(db, project, tmp_path)
    out = {
        "status": "ok",
        "scope_ops": {"create": [{"id": "scope_new", "name": "New Direction"}]},
        "bugs": [_bug("scope_new")],
    }
    inserted = validate_and_ingest(db, run, out, min_findings=1, max_findings=5)
    # The bug's scope_id was rewritten to the real, project-qualified scope.
    assert inserted[0].scope_id.endswith(f"__{project.id}")
    assert db.get(Scope, inserted[0].scope_id) is not None


# ── rejections ────────────────────────────────────────────────────────────--
def test_ingest_rejects_non_dict_output(db, project, tmp_path):
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="not a JSON object"):
        validate_and_ingest(db, run, ["nope"], min_findings=1, max_findings=5)  # type: ignore[arg-type]


def test_ingest_rejects_bad_status(db, project, tmp_path):
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="invalid status"):
        validate_and_ingest(db, run, {"status": "maybe", "bugs": []}, min_findings=0, max_findings=5)


def test_ingest_propagates_harness_failure(db, project, tmp_path):
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="status=failed"):
        validate_and_ingest(
            db, run, {"status": "failed", "error": "boom"}, min_findings=0, max_findings=5
        )


def test_ingest_enforces_min_findings(db, project, tmp_path):
    _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="outside"):
        validate_and_ingest(db, run, {"status": "ok", "bugs": []}, min_findings=1, max_findings=5)


def test_ingest_enforces_max_findings(db, project, tmp_path):
    sid = _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    bugs = [_bug(sid, id=f"b{i}") for i in range(3)]
    with pytest.raises(SearcherOutputError, match="outside"):
        validate_and_ingest(db, run, {"status": "ok", "bugs": bugs}, min_findings=1, max_findings=2)


def test_ingest_rejects_bug_failing_schema(db, project, tmp_path):
    sid = _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    bad = _bug(sid)
    del bad["repro_usage"]  # required field missing
    with pytest.raises(SearcherOutputError, match="fails schema"):
        validate_and_ingest(db, run, {"status": "ok", "bugs": [bad]}, min_findings=1, max_findings=5)


def test_ingest_rejects_unresolvable_scope(db, project, tmp_path):
    _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="unresolved scope id"):
        validate_and_ingest(
            db, run, {"status": "ok", "bugs": [_bug("scope_ghost")]},
            min_findings=1, max_findings=5,
        )


def test_ingest_rejects_when_project_has_no_scopes(db, project, tmp_path):
    run = _run(db, project, tmp_path)
    with pytest.raises(SearcherOutputError, match="no scopes defined"):
        validate_and_ingest(
            db, run, {"status": "ok", "bugs": [_bug("scope_x")]},
            min_findings=1, max_findings=5,
        )


def test_ingest_atomicity_no_partial_insert_on_bad_second_bug(db, project, tmp_path):
    sid = _seed_scope(db, project)
    run = _run(db, project, tmp_path)
    good = _bug(sid, id="good")
    bad = _bug("scope_ghost", id="bad")  # unresolvable
    with pytest.raises(SearcherOutputError):
        validate_and_ingest(
            db, run, {"status": "ok", "bugs": [good, bad]}, min_findings=1, max_findings=5
        )
    # Validation happens before any insert, so the DB stays clean.
    assert db.query(Bug).count() == 0
