from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


def data_root() -> Path:
    root = get_settings().data_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_dir(project_id: str) -> Path:
    p = data_root() / f"project_{project_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_dir(role: str, identifier: str) -> Path:
    """
    Run artifact directory.

    role in {searcher_agent, cleaner_agent, critical_thinking_agent}.
    identifier is the run id (or review id for cleaner runs).
    """
    prefix = {
        "searcher_agent": "searcher",
        "cleaner_agent": "cleaner",
        "critical_thinking_agent": "critical",
    }[role]
    p = data_root() / f"{prefix}_{identifier}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def write_text(path: Path, text: str) -> Path:
    path.write_text(text)
    return path
