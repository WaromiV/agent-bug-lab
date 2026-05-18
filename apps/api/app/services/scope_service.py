from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import next_id
from app.core.logging import get_logger
from app.db.models import Scope
from app.schemas.scope import ScopeCreate, ScopePatch

log = get_logger(__name__)


@dataclass(frozen=True)
class PreliminaryScope:
    seed_id: str
    name: str
    description: str


# The seed vocabulary every new project gets. Agents may add to this freely
# but may not delete entries. Keep aligned with migration 0003_scope_ownership.
PRELIMINARY_SCOPES: tuple[PreliminaryScope, ...] = (
    PreliminaryScope("scope_memory_safety",          "Memory safety",          "Buffer overflows, use-after-free, double free, integer overflows, OOB read/write."),
    PreliminaryScope("scope_authentication",         "Authentication",         "Authentication boundary issues, credential handling, session establishment."),
    PreliminaryScope("scope_authorization",          "Authorization",          "Privilege boundaries, permission checks, capability/role enforcement."),
    PreliminaryScope("scope_input_validation",       "Input validation",       "Injection sinks (SQL, command, SSTI), SSRF, deserialization, missing/weak validation."),
    PreliminaryScope("scope_cryptography",           "Cryptography",           "Weak / misused / predictable / homegrown crypto, key handling, RNG quality."),
    PreliminaryScope("scope_ipc_boundary",           "IPC trust boundary",     "Privilege/process-boundary IPC: parent-trusts-child, validation gaps on IPC messages."),
    PreliminaryScope("scope_race_conditions",        "Race conditions",        "TOCTOU, data races, lock ordering, atomicity violations."),
    PreliminaryScope("scope_denial_of_service",      "Denial of service",      "Resource exhaustion, unbounded growth, panic / crash paths."),
    PreliminaryScope("scope_information_disclosure", "Information disclosure", "Side channels, error/log leaks, unintended cross-origin exposure."),
    PreliminaryScope("scope_supply_chain",           "Supply chain",           "Dependency / build / update / signing / distribution weaknesses."),
    PreliminaryScope("scope_logic_flaws",            "Logic flaws",            "Business-logic, state-machine, invariant violations not covered above."),
)


class ScopeOpsError(ValueError):
    pass


def list_for_project(db: Session, project_id: str) -> list[Scope]:
    return list(
        db.execute(
            select(Scope).where(Scope.project_id == project_id).order_by(Scope.created_at)
        ).scalars()
    )


def get(db: Session, scope_id: str) -> Scope | None:
    return db.get(Scope, scope_id)


def create(db: Session, *, project_id: str, payload: ScopeCreate, explicit_id: str | None = None) -> Scope:
    if explicit_id and db.get(Scope, explicit_id) is not None:
        raise ScopeOpsError(f"scope id already exists: {explicit_id}")
    s = Scope(
        id=explicit_id or next_id(db, "scope"),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(s)
    db.flush()
    log.info("scope.created", scope_id=s.id, project_id=project_id, name=s.name)
    return s


def patch(db: Session, scope: Scope, payload: ScopePatch) -> Scope:
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(scope, k, v)
    db.flush()
    log.info("scope.renamed", scope_id=scope.id, name=scope.name)
    return scope


def seed_preliminary_scopes(db: Session, project_id: str) -> list[Scope]:
    """Idempotently insert the PRELIMINARY_SCOPES vocabulary for this project."""
    existing_names = {s.name for s in list_for_project(db, project_id)}
    seeded: list[Scope] = []
    for p in PRELIMINARY_SCOPES:
        if p.name in existing_names:
            continue
        seeded.append(
            create(
                db,
                project_id=project_id,
                payload=ScopeCreate(name=p.name, description=p.description),
                explicit_id=f"{p.seed_id}__{project_id}",
            )
        )
    if seeded:
        log.info("scopes.preliminary_seeded", project_id=project_id, count=len(seeded))
    return seeded


def apply_scope_ops(db: Session, project_id: str, scope_ops: Any) -> dict[str, str]:
    """
    Process the optional `scope_ops` block from an agent output. Returns a
    mapping from any agent-supplied id (in scope_ops.create) to the *real*
    scope id stored in the DB — call sites can use this to rewrite bug
    payloads that referenced the new ids before they existed.

    Operations supported: `create`, `rename`. Deletion is **never** honored.
    Unknown operations are ignored with a log line.
    """
    if scope_ops is None:
        return {}
    if not isinstance(scope_ops, dict):
        raise ScopeOpsError("scope_ops must be an object")

    id_map: dict[str, str] = {}

    for op in scope_ops.get("create") or []:
        if not isinstance(op, dict):
            raise ScopeOpsError("scope_ops.create[*] must be objects")
        name = (op.get("name") or "").strip()
        if not name:
            raise ScopeOpsError("scope_ops.create[*].name is required")
        description = op.get("description") or None
        requested_id = op.get("id")

        existing = next(
            (s for s in list_for_project(db, project_id) if s.name.lower() == name.lower()),
            None,
        )
        if existing is not None:
            log.info("scope.create.coalesced_into_existing", scope_id=existing.id, name=name)
            if requested_id:
                id_map[requested_id] = existing.id
            continue

        explicit_id: str | None = None
        if requested_id:
            qualified = (
                requested_id
                if requested_id.endswith(f"__{project_id}")
                else f"{requested_id}__{project_id}"
            )
            if db.get(Scope, qualified) is None:
                explicit_id = qualified

        new_scope = create(
            db,
            project_id=project_id,
            payload=ScopeCreate(name=name, description=description),
            explicit_id=explicit_id,
        )
        if requested_id:
            id_map[requested_id] = new_scope.id

    for op in scope_ops.get("rename") or []:
        if not isinstance(op, dict):
            raise ScopeOpsError("scope_ops.rename[*] must be objects")
        sid = op.get("id")
        if not sid:
            raise ScopeOpsError("scope_ops.rename[*].id is required")
        target = db.get(Scope, sid)
        if target is None or target.project_id != project_id:
            raise ScopeOpsError(f"scope_ops.rename: scope {sid!r} not found in project {project_id!r}")
        patch_payload: dict[str, Any] = {}
        if "name" in op:
            new_name = (op.get("name") or "").strip()
            if not new_name:
                raise ScopeOpsError(f"scope_ops.rename[{sid}].name is empty")
            patch_payload["name"] = new_name
        if "description" in op:
            patch_payload["description"] = op["description"]
        if patch_payload:
            patch(db, target, ScopePatch(**patch_payload))

    if scope_ops.get("delete"):
        log.warning(
            "scope_ops.delete.ignored",
            project_id=project_id,
            count=len(scope_ops["delete"]),
        )

    return id_map


def resolve_scope_id(db: Session, project_id: str, scope_id: str, id_map: dict[str, str]) -> str:
    """Resolve a possibly-temporary scope id reference to the real DB id."""
    if scope_id in id_map:
        return id_map[scope_id]
    if db.get(Scope, scope_id) is not None:
        return scope_id
    # tolerate the un-suffixed semantic prefix
    qualified = f"{scope_id}__{project_id}"
    if db.get(Scope, qualified) is not None:
        return qualified
    raise ScopeOpsError(f"unresolved scope id: {scope_id!r}")


def ensure_default(db: Session, project_id: str, name: str) -> Scope:
    """Return the project's first scope, seeding the preliminary set if empty."""
    existing = list_for_project(db, project_id)
    if existing:
        return existing[0]
    seeded = seed_preliminary_scopes(db, project_id)
    return seeded[0]
