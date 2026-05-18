from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


class UnsafePathError(ValueError):
    pass


def ensure_under_fixed_repo_root(path: str | Path) -> Path:
    """Resolve `path` and verify it lives under FIXED_REPO_ROOT.

    Used as a defence-in-depth check before handing a path to a harness.
    """
    root = get_settings().fixed_repo_root.resolve()
    candidate = Path(path).resolve()
    if candidate != root and root not in candidate.parents:
        raise UnsafePathError(f"path {candidate} escapes FIXED_REPO_ROOT {root}")
    return candidate
