from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_PREFIX = {
    "project": "project",
    "scope": "scope",
    "run": "run",
    "bug": "bug",
    "review": "review",
    "debate": "debate",
    "dturn": "dturn",
}

_SEQUENCE = {
    "project": "project_id_seq",
    "scope": "scope_id_seq",
    "run": "run_id_seq",
    "bug": "bug_id_seq",
    "review": "review_id_seq",
    "debate": "debate_id_seq",
    "dturn": "dturn_id_seq",
}


def next_id(session: Session, kind: str) -> str:
    """Allocate the next zero-padded id from a Postgres sequence."""
    seq = _SEQUENCE[kind]
    value = session.execute(text(f"SELECT nextval('{seq}')")).scalar_one()
    return f"{_PREFIX[kind]}_{int(value):06d}"
